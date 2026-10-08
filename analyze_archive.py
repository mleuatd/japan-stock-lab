#!/usr/bin/env python3
"""Private offline daily rankings from existing J-Quants CSV archives.
Print only to the local authenticated operator; NEVER publish results to Pages.
Usage: python analyze_archive.py --root archive/daily --date 2025-06-25
"""
import argparse,csv,gzip
from pathlib import Path

def rankings(root):
    previous={}
    streak={}
    for path in sorted(Path(root).rglob("*.csv.gz")):
        date=path.name.removesuffix(".csv.gz")
        current={}
        changes=[]
        with gzip.open(path,"rt",encoding="utf-8",newline="") as handle:
            for row in csv.DictReader(handle):
                code=row["Code"];price=float(row["AdjC"]) if row["AdjC"] else None
                old=previous.get(code)
                if old is not None and old>0 and price is not None:
                    changes.append((code,round((price/old-1)*100,4)))
                current[code]=price
        changes.sort(key=lambda r:(-r[1],r[0]))
        top=changes[:30]
        streak={code:streak.get(code,0)+1 for code,_ in top}
        yield date,[{"rank":i,"code":code,"change_percent":change,"consecutive_top30":streak[code]}
                    for i,(code,change) in enumerate(top,1)]
        previous=current

def main():
    import json
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="archive/daily")
    p.add_argument("--date",required=True)
    a=p.parse_args()
    matches=[rows for date,rows in rankings(a.root) if date==a.date]
    if not matches: raise SystemExit("Requested date not available in private archive")
    print(json.dumps({"date":a.date,"top30":matches[0]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
