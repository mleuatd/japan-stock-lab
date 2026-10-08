#!/usr/bin/env python3
"""J-Quants V2 delayed daily-bars exporter. No broker orders."""
import argparse, csv, datetime as dt, gzip, io, json, os, pathlib, random, time, urllib.error, urllib.parse, urllib.request

URL = "https://api.jquants.com/v2/equities/bars/daily"
FIELDS = ["Date","Code","O","H","L","C","Vo","Va","AdjC","AdjFactor"]

def fetch_day(day, key):
    results, cursor, seen = [], None, set()
    while True:
        query = {"date": day.isoformat()}
        if cursor: query["pagination_key"] = cursor
        req = urllib.request.Request(URL+"?"+urllib.parse.urlencode(query), headers={"x-api-key": key, "User-Agent":"japan-stock-lab/1"})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=60) as r: payload=json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (400,401,403): raise RuntimeError("API access denied (HTTP %d)" % e.code) from None
                if e.code not in (429,500,502,503,504) or attempt==5: raise
            except (urllib.error.URLError,TimeoutError):
                if attempt==5: raise
            time.sleep(min(120,3*2**attempt)+random.random())
        rows=payload.get("data")
        if not isinstance(rows,list): raise RuntimeError("Unexpected API response schema")
        results.extend(rows)
        cursor=payload.get("pagination_key")
        if not cursor: return results
        if cursor in seen: raise RuntimeError("Repeated pagination cursor")
        seen.add(cursor)

def save_day(day, rows, root):
    if not rows: return False
    folder=root/day.strftime("%Y/%m")
    folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(day.isoformat()+".csv.gz")
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,extrasaction="ignore",lineterminator="\n")
    writer.writeheader()
    seen=set()
    for row in sorted(rows,key=lambda r:str(r.get("Code",""))):
        if row.get("Date")!=day.isoformat(): raise ValueError("Date mismatch")
        identity=(row.get("Date"),row.get("Code"))
        if identity in seen: raise ValueError("Duplicate ticker")
        seen.add(identity)
        writer.writerow(row)
    tmp=dest.with_suffix(".tmp")
    with tmp.open("wb") as handle:
        with gzip.GzipFile(filename="",mode="wb",fileobj=handle,mtime=0) as zipped:
            zipped.write(buf.getvalue().encode())
    os.replace(tmp,dest)
    return True

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--start");p.add_argument("--end")
    p.add_argument("--days",type=int,default=20)
    p.add_argument("--out",default="archive/daily")
    args=p.parse_args()
    key=os.getenv("JQUANTS_API_KEY")
    if not key: raise SystemExit("JQUANTS_API_KEY not available in Actions Secrets")
    today=dt.date.today()
    first=dt.date.fromisoformat(args.start) if args.start else today-dt.timedelta(days=730)
    last=dt.date.fromisoformat(args.end) if args.end else today-dt.timedelta(weeks=12)
    root=pathlib.Path(args.out)
    if first>last: raise SystemExit("Invalid date range")
    fetched=missing=skipped=attempted=0
    date=first
    while date<=last:
        if date.weekday()<5:
            output=root/date.strftime("%Y/%m")/(date.isoformat()+".csv.gz")
            if output.exists(): skipped+=1
            elif attempted<args.days:
                attempted+=1
                rows=fetch_day(date,key)
                if save_day(date,rows,root):
                    fetched+=1;print("SAVED",date,len(rows),flush=True)
                else:
                    missing+=1;print("NO_DATA",date,flush=True)
                time.sleep(13)
            else: break
        date+=dt.timedelta(days=1)
    print(json.dumps(dict(fetched=fetched,missing=missing,skipped=skipped,attempted=attempted)))
if __name__=="__main__":run()
