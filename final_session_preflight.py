#!/usr/bin/env python3
"""Read-only final-session completeness preflight for private Neon data.

No ticker identifiers, licensed OHLC records or secrets in stdout.
"""
import json
import os

FINAL_COVERAGE_SQL = """
WITH latest AS (SELECT MAX(trading_date) AS d FROM daily_bar),
recent AS (
SELECT
 (SELECT d FROM latest)::text AS last_day,
 COUNT(*) FILTER (WHERE trading_date=(SELECT d FROM latest)) AS final_rows,
 COUNT(*) FILTER (WHERE trading_date=(SELECT d FROM latest)
     AND close_price IS NOT NULL AND close_price>0) AS final_valid_closes,
 COUNT(*) FILTER (WHERE trading_date=(SELECT d FROM latest)
     AND (open_price IS NULL OR close_price IS NULL
          OR adjusted_close IS NULL OR volume IS NULL)) AS final_incomplete_rows,
 COUNT(DISTINCT security_code) FILTER (WHERE trading_date >=
       (SELECT d FROM latest)-INTERVAL '14 days') AS recent_symbols
FROM daily_bar)
SELECT * FROM recent
"""

def summarize(row):
    values={key:int(row[key]) for key in
            ("final_rows","final_valid_closes","final_incomplete_rows","recent_symbols")}
    values["last_day"]=str(row["last_day"]) if row["last_day"] else None
    values["recent_symbols_not_on_final_day"]=max(0,values["recent_symbols"]-values["final_rows"])
    values["final_close_missing_or_invalid"]=values["final_rows"]-values["final_valid_closes"]
    values["mark_to_market_risk"]=bool(
        values["final_close_missing_or_invalid"] or
        values["recent_symbols_not_on_final_day"])
    values["result"]="AGGREGATE_ONLY_NOT_PORTFOLIO_VERIFIED"
    return values

def main():
    import psycopg
    uri=os.environ.get("DATABASE_URL")
    if not uri:raise RuntimeError("DATABASE_URL missing")
    with psycopg.connect(uri,sslmode="require") as conn:
        with conn.cursor() as cur:
            cur.execute(FINAL_COVERAGE_SQL)
            keys=[d.name for d in cur.description]
            record=dict(zip(keys,cur.fetchone()))
    print("FINAL_DAY_COVERAGE "+json.dumps(summarize(record),ensure_ascii=False))

if __name__=="__main__":main()
