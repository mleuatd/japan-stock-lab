#!/usr/bin/env python3
"""Read-only, aggregate-only quality gate for the private Neon stock archive.

Never print individual licensed stock price records or connection strings.
No trading, no modifications of database state. A quality report is diagnostic,
NOT a certification of accounting or backtest returns.
"""
import argparse
import json
import os

QUERY = """
SELECT
  COUNT(*) AS total,
  MIN(trading_date)::text AS first_date,
  MAX(trading_date)::text AS last_date,
  COUNT(DISTINCT security_code) AS symbols,
  COUNT(*) FILTER (WHERE trading_date > %s) AS holdout_rows,
  COUNT(*) FILTER (WHERE trading_date > %s AND adjustment_factor IS DISTINCT FROM 1)
       AS holdout_nonunit_factor_rows,
  COUNT(*) FILTER (WHERE adjustment_factor IS DISTINCT FROM 1)
       AS nonunit_factor_rows,
  COUNT(*) FILTER (WHERE open_price IS NULL OR close_price IS NULL
                    OR adjusted_close IS NULL OR volume IS NULL) AS required_null_rows,
  COUNT(*) FILTER (WHERE open_price <= 0 OR close_price <= 0
                    OR adjusted_close <= 0 OR volume < 0) AS invalid_value_rows,
  COUNT(*) FILTER (WHERE trading_date > %s AND
                    (open_price IS NULL OR close_price IS NULL
                     OR adjusted_close IS NULL OR volume IS NULL))
       AS holdout_required_null_rows,
  COUNT(*) FILTER (WHERE trading_date > %s AND
                    (open_price <= 0 OR close_price <= 0
                     OR adjusted_close <= 0 OR volume < 0))
       AS holdout_invalid_value_rows
FROM daily_bar
"""

def summarize(row, cutoff="2026-01-30", maximum_lag_days=10, today=None):
    from datetime import date
    now=date.fromisoformat(today) if today else date.today()
    last=date.fromisoformat(str(row["last_date"])) if row["last_date"] else None
    lag=(now-last).days if last else None
    output={"cutoff":cutoff,"records":int(row["total"]),
            "first_date":str(row["first_date"]) if row["first_date"] else None,
            "last_date":str(row["last_date"]) if last else None,
            "symbols":int(row["symbols"]),
            "holdout_rows":int(row["holdout_rows"]),
            "nonunit_factor_rows":int(row["nonunit_factor_rows"]),
            "holdout_nonunit_factor_rows":int(row["holdout_nonunit_factor_rows"]),
            "required_null_rows":int(row["required_null_rows"]),
            "invalid_value_rows":int(row["invalid_value_rows"]),
            "holdout_required_null_rows":int(row["holdout_required_null_rows"]),
            "holdout_invalid_value_rows":int(row["holdout_invalid_value_rows"]),
            "data_age_calendar_days":lag,
            "stale":lag is None or lag>maximum_lag_days}
    # These are rows with unusual factors, NOT confirmed split/merger events.
    issues=[]
    if output["stale"]:issues.append("STALE_DATA")
    if output["required_null_rows"] or output["invalid_value_rows"]:
        issues.append("INVALID_OR_INCOMPLETE_BAR_ROWS")
    if output["nonunit_factor_rows"]:
        issues.append("CORPORATE_ACTION_RECONCILIATION_REQUIRED")
    if output["holdout_rows"]==0:issues.append("NO_HOLDOUT_DATA")
    output["blocking_issues"]=issues
    output["validation_status"]="PROVISIONAL_UNVERIFIED"
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cutoff",default="2026-01-30")
    p.add_argument("--max-lag-days",type=int,default=10)
    a=p.parse_args()
    if a.max_lag_days<0:raise ValueError("max-lag-days cannot be negative")
    uri=os.environ.get("DATABASE_URL")
    if not uri:raise RuntimeError("DATABASE_URL is missing")
    import psycopg
    with psycopg.connect(uri,sslmode="require") as db:
        with db.cursor() as cursor:
            cursor.execute(QUERY,(a.cutoff,)*4)
            names=[d.name for d in cursor.description]
            row=dict(zip(names,cursor.fetchone()))
    print(json.dumps(summarize(row,a.cutoff,a.max_lag_days),ensure_ascii=False))

if __name__=="__main__":
    main()
