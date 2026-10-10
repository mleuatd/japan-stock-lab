#!/usr/bin/env python3
"""Local-only export for the owner's PRIVATE Neon fund ledger.

Requirements: psycopg >=3; DATABASE_URL env var configured by user.
Never logs fund rows or uploads private data to public GitHub.
  python personal_fund_local_backup.py --output-dir /private/path
"""
import argparse
import csv
import json
import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

TABLES = (
    "personal_fund_source", "personal_fund_catalog",
    "personal_fund_estimated_purchase", "personal_fund_snapshot",
    "personal_fund_position", "personal_fund_recurring_plan",
    "personal_fund_annual_estimate",
)
VIEWS = (
    "personal_fund_snapshot_summary", "personal_fund_monthly_chart",
    "personal_fund_asset_history_for_chart", "personal_fund_position_change",
)

def safe_output_path(path, repo_dir):
    """Refuse output in any directory inside the public source repository."""
    p = Path(path).expanduser().resolve()
    r = Path(repo_dir).resolve()
    if p == r or r in p.parents:
        raise ValueError("Private reports must not be written into public repository")
    return p

def stringify(v):
    if v is None:
        return None
    if isinstance(v, (date, datetime, Decimal)):
        return str(v)
    return v

def table_rows(conn, name):
    if name not in TABLES + VIEWS:
        raise ValueError("Unexpected relation name")
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM "' + name + '"')
        columns = [d.name for d in cur.description]
        return columns, [[stringify(v) for v in row] for row in cur.fetchall()]

def save_sqlite(path, tables):
    with sqlite3.connect(path) as db:
        for name, (columns, rows) in tables.items():
            keys = ','.join('"' + c.replace('"','""') + '" TEXT' for c in columns)
            db.execute('CREATE TABLE "' + name + '" (' + keys + ')')
            if rows:
                db.executemany('INSERT INTO "' + name + '" VALUES (' +
                               ','.join('?' for _ in columns) + ')',
                               [[None if v is None else str(v) for v in row] for row in rows])
        db.commit()

def svg_chart(columns, rows):
    """Self-contained offline SVG chart and accessible text description."""
    find = {name:i for i,name in enumerate(columns)}
    req = ("month_key","invested_yen","market_value_yen","pnl_yen")
    if any(k not in find for k in req):
        raise ValueError("Missing graph columns")
    history = [(str(r[find["month_key"]])[:7],
                float(r[find["invested_yen"]]),
                float(r[find["market_value_yen"]]),
                float(r[find["pnl_yen"]])) for r in rows]
    if not history:
        raise ValueError("No history to graph")
    history.sort(key=lambda x:x[0])
    width,height,left,top,right,bottom = 1100,530,110,70,50,90
    plot_w=width-left-right; plot_h=height-top-bottom
    low=min(0,min(min(t[1:]) for t in history))
    high=max(1,max(max(t[1:]) for t in history))*1.06
    def xy(i,y):
        x=left + plot_w*i/max(1,len(history)-1)
        yy=top+plot_h*(high-y)/(high-low)
        return f"{x:.1f},{yy:.1f}"
    desc="; ".join(f"{d}: invested JPY {a:,.0f}, assets JPY {b:,.0f}, gain JPY {c:,.0f}"
                     for d,a,b,c in history)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
           '<title>Historical personal investment fund portfolio in Japanese yen</title>',
           f'<desc>{escape(desc)}</desc>',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="110" y="35" font-size="23">Investment fund portfolio / archived and modeled values</text>',
           f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#777"/>']
    for k,(label,idx,color) in enumerate((("Total assets",2,"#115e59"),
                                            ("Invested",1,"#2563eb"),
                                            ("Unrealized gain",3,"#b45309"))):
        points=" ".join(xy(i,h[idx]) for i,h in enumerate(history))
        parts.append(f'<polyline points="{points}" stroke="{color}" stroke-width="3" fill="none"/>')
        parts.append(f'<text x="{left+k*300}" y="{height-23}" fill="{color}" font-size="18">{label}</text>')
    for i,(d,*_) in enumerate(history):
        if i==0 or i==len(history)-1 or i%2==0:
            x=left+plot_w*i/max(1,len(history)-1)
            parts.append(f'<text x="{x:.1f}" y="{height-57}" text-anchor="middle" font-size="12">{escape(d)}</text>')
    for k in range(5):
        y=low+(high-low)*k/4
        yy=top+plot_h*(1-k/4)
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{left+plot_w}" y2="{yy:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{left-9}" y="{yy+5:.1f}" text-anchor="end" font-size="13">{y/1000000:.1f}M</text>')
    parts.append(f'<text x="15" y="53" font-size="12">JPY million</text>')
    parts.append('<text x="105" y="506" font-size="12">Older annual points are model estimates. Latest point uses screenshot receipt month, not verified valuation date.</text>')
    parts.append('</svg>')
    return "\n".join(parts)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",required=True,
                    help="Absolute PRIVATE directory, outside public GitHub repo")
    args=ap.parse_args()
    output=safe_output_path(args.output_dir,Path(__file__).parent)
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is missing")
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Refusing to overwrite a non-empty backup destination")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"],sslmode="require") as conn:
        all_data={name:table_rows(conn,name) for name in TABLES + VIEWS}
    output.mkdir(parents=True,exist_ok=True)
    save_sqlite(output/"personal_funds.sqlite3",all_data)
    for name in ("personal_fund_snapshot_summary","personal_fund_monthly_chart",
                 "personal_fund_asset_history_for_chart"):
        columns,rows=all_data[name]
        with (output/(name+".csv")).open("w",newline="",encoding="utf-8-sig") as f:
            csvwriter=csv.writer(f);csvwriter.writerow(columns);csvwriter.writerows(rows)
    col,rows=all_data["personal_fund_asset_history_for_chart"]
    (output/"fund_history.svg").write_text(svg_chart(col,rows),encoding="utf-8")
    counts={name:len(all_data[name][1]) for name in TABLES}
    (output/"manifest.json").write_text(
        json.dumps({"created_utc":datetime.utcnow().isoformat()+"Z","tables":counts,
                    "notice":"Private data. Model estimates are NOT actual broker fills."},
                   ensure_ascii=False,indent=2),encoding="utf-8")
    print("Private backup exported locally; source tables:",len(counts),
          "monthly modeled purchases:",counts["personal_fund_estimated_purchase"])

if __name__=="__main__":
    main()
