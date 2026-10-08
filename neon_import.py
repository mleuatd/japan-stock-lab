#!/usr/bin/env python3
"""Private, restartable CSV.gz -> PostgreSQL importer; no live API calls or brokerage orders.

Setup: pip install 'psycopg[binary]>=3,<4'
Set DATABASE_URL in a secure environment (never in a public repository).
Preview: python neon_import.py --root archive/daily
Import:  python neon_import.py --root archive/daily --apply
"""
import argparse
import csv
import gzip
import hashlib
import os
from pathlib import Path
from decimal import Decimal, InvalidOperation

COLUMNS = ("Date","Code","O","H","L","C","Vo","Va","AdjC","AdjFactor")
INSERT = """INSERT INTO daily_bar
(trading_date,security_code,open_price,high_price,low_price,close_price,
 volume,trading_value,adjusted_close,adjustment_factor)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (trading_date,security_code) DO NOTHING"""
SCHEMA = Path(__file__).parent / "sql" / "001_init.sql"

def decode_day(path):
    date = path.name.removesuffix(".csv.gz")
    import datetime
    if datetime.date.fromisoformat(date).isoformat() != date:
        raise ValueError("invalid date filename")
    rows = []
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"invalid CSV header: {path}")
        for r in reader:
            if r["Date"] != date or not r["Code"] or r["Code"] in seen:
                raise ValueError(f"invalid or duplicate date/code: {path}")
            seen.add(r["Code"])
            values = [None if r[k] in ("",None) else r[k] for k in COLUMNS]
            if values[6] is not None:
                try:
                    volume = Decimal(values[6])
                    if not volume.is_finite() or volume < 0 or volume != volume.to_integral_value():
                        raise ValueError("volume must be a nonnegative whole number")
                    values[6] = int(volume)
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError(f"invalid volume in {path}") from exc
            rows.append(tuple(values))
    if not rows:
        raise ValueError(f"empty day: {path}")
    return date, rows

def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="archive/daily")
    ap.add_argument("--apply",action="store_true",help="Actually insert into private Postgres")
    ap.add_argument("--max-days",type=int,default=5,help="Maximum new trading days per run (default 5)")
    args=ap.parse_args()
    if args.max_days < 1 or args.max_days > 20:
        raise SystemExit("--max-days must be 1..20 for safe incremental Neon Free imports")
    paths=sorted(Path(args.root).rglob("*.csv.gz"))
    if not paths:
        raise SystemExit("No source CSV.gz files; existing archive is required")
    print(f"Found {len(paths)} daily archive files", flush=True)
    if not args.apply:
        print("DRY RUN: no database changes; pass --apply after setting DATABASE_URL")
        return
    url=os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set (never commit database credentials)")
    import psycopg
    with psycopg.connect(url, sslmode="require") as con:
        # initialize once; never DROP or TRUNCATE
        with con.transaction():
            schema_lines = (line for line in SCHEMA.read_text(encoding="utf-8").splitlines()
                            if not line.lstrip().startswith("--"))
            for statement in "\n".join(schema_lines).split(";"):
                if statement.strip():
                    con.execute(statement)
        imported=skipped=0
        for path in paths:
            if imported >= args.max_days:
                print("Batch limit reached; resume next run", flush=True)
                break
            size=con.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            if size >= 700_000_000:
                raise SystemExit("STOP: DB >= 700MB safety threshold; no further imports")
            date=path.name.removesuffix(".csv.gz")
            # Only complete dates are skipped: avoid re-import and API re-fetch.
            state=con.execute("SELECT state FROM ingest_day WHERE trading_date=%s",(date,)).fetchone()
            if state and state[0]=="complete":
                skipped+=1
                continue
            day,rows=decode_day(path)
            digest=checksum(path)
            with con.transaction():
                with con.cursor() as cur:
                    cur.executemany(INSERT,rows)
                    # Mark complete only after every row passes insertion.
                    actual=cur.execute("SELECT COUNT(*) FROM daily_bar WHERE trading_date=%s",(day,)).fetchone()[0]
                    if actual != len(rows):
                        raise ValueError(f"row count differs for {day}: {actual} != {len(rows)}")
                    cur.execute("""INSERT INTO ingest_day
                        (trading_date,state,rows_count,payload_checksum,source)
                        VALUES (%s,'complete',%s,%s,'jquants-csv-gzip')
                        ON CONFLICT (trading_date) DO UPDATE SET
                        state=EXCLUDED.state,rows_count=EXCLUDED.rows_count,
                        payload_checksum=EXCLUDED.payload_checksum,
                        source=EXCLUDED.source,collected_at=now()""",(day,len(rows),digest))
            imported+=1
            print(f"IMPORTED {day} {len(rows)}",flush=True)
        print(f"Complete: {imported} new days; {skipped} previously complete days")
if __name__=="__main__":
    main()
