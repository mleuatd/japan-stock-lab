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
FROM daily_bar),
missing AS (
 SELECT b.security_code FROM daily_bar b, latest l
 WHERE b.trading_date=l.d AND (b.close_price IS NULL OR b.close_price<=0)
),
previous AS (
 SELECT m.security_code, MAX(b.trading_date) prior_close_date
 FROM missing m
 LEFT JOIN daily_bar b ON b.security_code=m.security_code
   AND b.trading_date<(SELECT d FROM latest) AND b.close_price>0
 GROUP BY m.security_code
),
missing_summary AS (
 SELECT COUNT(*) AS invalid_final_closes,
 COUNT(*) FILTER (WHERE prior_close_date IS NOT NULL) AS previously_quoted,
 COUNT(*) FILTER (WHERE prior_close_date IS NULL) AS never_quoted
 FROM previous
)
SELECT * FROM recent CROSS JOIN missing_summary
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
    if row.get("invalid_final_closes") is not None:
        for k in ("invalid_final_closes","previously_quoted","never_quoted"):
            values[k]=int(row[k])
        if values["invalid_final_closes"] != values["previously_quoted"]+values["never_quoted"]:
            raise ValueError("Final close deficiency categories do not reconcile")
        if values["invalid_final_closes"] != values["final_close_missing_or_invalid"]:
            raise ValueError("Final close aggregate disagrees with final-day count")
        values["external_price_source_required"]=values["never_quoted"]>0
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
