#!/usr/bin/env python3
"""Validate locally stored J-Quants daily CSV gzip files without publishing data."""
import argparse
import csv
import gzip
import json
from pathlib import Path

REQUIRED = ("Date", "Code", "O", "H", "L", "C", "Vo", "Va", "AdjC", "AdjFactor")
NUMERIC = ("O", "H", "L", "C", "Vo", "Va", "AdjC", "AdjFactor")

def audit(root):
    files = sorted(Path(root).rglob("*.csv.gz"))
    if not files:
        raise ValueError("No daily CSV files available")
    summary = {"files": len(files), "rows": 0, "distinct_codes": 0, "null_close_rows": 0, "min_date": None, "max_date": None}
    codes = set()
    dates = set()
    for path in files:
        expected = path.name.removesuffix(".csv.gz")
        if expected in dates:
            raise ValueError(f"Duplicate date file: {expected}")
        dates.add(expected)
        seen = set()
        with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if tuple(reader.fieldnames or ()) != REQUIRED:
                raise ValueError(f"Unexpected columns: {path}")
            count = 0
            for line, row in enumerate(reader, start=2):
                code = row.get("Code")
                if row.get("Date") != expected or not code:
                    raise ValueError(f"Invalid date or code: {path}:{line}")
                if code in seen:
                    raise ValueError(f"Duplicate code: {path}:{line}")
                seen.add(code)
                codes.add(code)
                for field in NUMERIC:
                    value = row.get(field)
                    if value not in (None, ""):
                        try:
                            number = float(value)
                        except ValueError as exc:
                            raise ValueError(f"Bad numeric value {field}: {path}:{line}") from exc
                        if not (-float("inf") < number < float("inf")):
                            raise ValueError(f"Non-finite number {field}: {path}:{line}")
                if row["C"] in (None, ""):
                    summary["null_close_rows"] += 1  # valid for stocks without trades
                count += 1
        if count == 0:
            raise ValueError(f"Empty daily CSV: {path}")
        summary["rows"] += count
    summary["distinct_codes"] = len(codes)
    summary["min_date"] = min(dates)
    summary["max_date"] = max(dates)
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="archive/daily")
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.root), ensure_ascii=False))
    except (ValueError, OSError, EOFError) as exc:
        parser.exit(1, f"VALIDATION FAILED: {exc}\n")
