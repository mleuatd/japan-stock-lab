#!/usr/bin/env python3
"""Repeatable *joint-condition* 1..30-session historical price forecast.

The 16-pattern marginal table cannot yield statistics for an intersection such
as HIGH20 & SMA_BULL. Compute the intersection from private daily_bar with
only prior/current information and explicitly observed future horizons.

Descriptive historical scenarios, NOT calibrated stock-price predictions.
No brokerage orders, no public raw market-price output and no live price feed.
"""
import argparse
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

from jpx_market_risk import risk_as_of_close
from pattern_forward_stats import DEFINITIONS, detect, wilson

PATTERN_SQL = {
 "BASE": "b.volume>0",
 "UP3": "adj>p1 AND p1>p2 AND p2>p3",
 "DOWN3": "adj<p1 AND p1<p2 AND p2<p3",
 "UP5": "adj>p1 AND p1>p2 AND p2>p3 AND p3>p4 AND p4>p5",
 "DOWN5": "adj<p1 AND p1<p2 AND p2<p3 AND p3<p4 AND p4<p5",
 "GAIN5": "adj>=p5*1.05",
 "LOSS5": "adj<=p5*0.95",
 "DIP_REV": "adj<=p5*0.97 AND adj>p1",
 "RALLY_DIP": "adj>=p5*1.03 AND adj<p1",
 "HIGH20": "adj>max_prev20",
 "LOW20": "adj<min_prev20",
 "SMA_BULL": "avg5>avg20",
 "SMA_BEAR": "avg5<avg20",
 "SIDEWAYS": "max_20<=min_20*1.06",
 "VOL_UP": "volume>=2*avg_prev_vol5 AND adj>p1 AND avg_prev_vol5>0",
 "VOL_DOWN": "volume>=2*avg_prev_vol5 AND adj<p1 AND avg_prev_vol5>0",
}
assert set(PATTERN_SQL)==set(DEFINITIONS)

def choose_patterns(pattern_codes):
    chosen=sorted(set(pattern_codes)-{"BASE"})
    if any(code not in PATTERN_SQL for code in chosen):
        raise ValueError("Unknown registered pattern code")
    return chosen

def detect_recent(bars,as_of):
    """Current quote rows must have dates; no fabricated non-trading rows."""
    if len(bars)!=21:
        raise ValueError("Provide exactly 21 consecutive reported trading-day bars")
    dates=[date.fromisoformat(x["date"]) for x in bars]
    if dates!=sorted(set(dates)):
        raise ValueError("Bar dates must be unique and ascending")
    if dates[-1].isoformat()!=as_of:
        raise ValueError("Most recent bar does not match requested as_of date")
    prices=[float(x["adjusted_close"]) for x in bars]
    volumes=[float(x["volume"]) for x in bars]
    codes=choose_patterns(detect(prices,volumes))
    if not math.isfinite(prices[-1]) or prices[-1]<=0:
        raise ValueError("Invalid reference adjusted close")
    return codes,prices[-1]

def build_sql(tags):
    """Only internal fixed SQL fragments selected by validated pattern ID."""
    tags=choose_patterns(tags)
    predicates=" AND ".join("("+PATTERN_SQL[c]+")" for c in tags) or "TRUE"
    return f"""WITH sessions AS (
 SELECT trading_date,ROW_NUMBER() OVER (ORDER BY trading_date) AS idx
 FROM (SELECT DISTINCT trading_date FROM daily_bar
       WHERE trading_date BETWEEN %s AND %s) dates
), obs AS (
 SELECT b.security_code,b.trading_date,s.idx,
 b.adjusted_close AS adj,b.volume,
 LAG(s.idx,20) OVER w AS prev_idx,
 LAG(b.adjusted_close,1) OVER w AS p1,
 LAG(b.adjusted_close,2) OVER w AS p2,
 LAG(b.adjusted_close,3) OVER w AS p3,
 LAG(b.adjusted_close,4) OVER w AS p4,
 LAG(b.adjusted_close,5) OVER w AS p5,
 MAX(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS max_prev20,
 MIN(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS min_prev20,
 MAX(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20,
 MIN(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20,
 AVG(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS avg5,
 AVG(b.adjusted_close) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg20,
 AVG(b.volume) OVER (PARTITION BY b.security_code ORDER BY b.trading_date
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_prev_vol5
 FROM daily_bar b JOIN sessions s USING(trading_date)
 WHERE b.trading_date BETWEEN %s AND %s AND
       b.adjusted_close>0 AND b.volume>=0
 WINDOW w AS (PARTITION BY b.security_code ORDER BY b.trading_date)
), qualified AS (
 SELECT *,ROW_NUMBER() OVER
   (PARTITION BY security_code,FLOOR(idx::numeric/30) ORDER BY idx) AS rn
 FROM obs b
 WHERE trading_date>=%s AND idx-prev_idx=20 AND volume>0
   AND {predicates}
   AND NOT (security_code='61730' AND trading_date>='2025-01-28'
        OR security_code='17260' AND trading_date>='2026-02-04'
        OR security_code='62010' AND trading_date>='2026-05-12')
), samples AS (
 SELECT security_code,idx,adj FROM qualified WHERE rn=1
), observations AS (
 SELECT h.horizon,s.adj AS reference_close,f.adjusted_close AS after_close,
 CASE WHEN nxt.idx IS NULL THEN 'unmatured'
      WHEN f.adjusted_close IS NULL OR f.adjusted_close<=0 THEN 'missing'
      ELSE 'observed' END AS category
 FROM samples s CROSS JOIN GENERATE_SERIES(1,30) AS h(horizon)
 LEFT JOIN sessions nxt ON nxt.idx=s.idx+h.horizon
 LEFT JOIN daily_bar f ON f.security_code=s.security_code
                        AND f.trading_date=nxt.trading_date
)
SELECT horizon,
 COUNT(*)::int AS total_events,
 COUNT(*) FILTER(WHERE category='observed')::int AS observed,
 COUNT(*) FILTER(WHERE category='unmatured')::int AS unmatured,
 COUNT(*) FILTER(WHERE category='missing')::int AS missing,
 COUNT(*) FILTER(WHERE category='observed' AND after_close>reference_close)::int AS up,
 COUNT(*) FILTER(WHERE category='observed' AND after_close<reference_close)::int AS down,
 COUNT(*) FILTER(WHERE category='observed' AND after_close=reference_close)::int AS flat,
 AVG(100.0*(after_close/reference_close-1))
       FILTER(WHERE category='observed') AS mean_pct,
 PERCENTILE_CONT(.5) WITHIN GROUP(ORDER BY 100.0*(after_close/reference_close-1))
       AS median_pct,
 PERCENTILE_CONT(.25) WITHIN GROUP(ORDER BY 100.0*(after_close/reference_close-1))
       AS p25_pct,
 PERCENTILE_CONT(.75) WITHIN GROUP(ORDER BY 100.0*(after_close/reference_close-1))
       AS p75_pct
 FROM observations GROUP BY horizon ORDER BY horizon"""

def summarize(rows,patterns,baseline,as_of,start,source_end):
    if not math.isfinite(baseline) or baseline<=0:
        raise ValueError("Invalid baseline price")
    if not rows or len(rows)!=30:
        raise ValueError("Expected actual result rows for all 30 future sessions")
    days=[]
    for (h,total,n,unmatured,missing,up,down,flat,mean,median,q25,q75) in rows:
        if total != n+unmatured+missing or up+down+flat!=n:
            raise AssertionError("Inconsistent historical outcomes")
        if h!=len(days)+1:
            raise AssertionError("Non-consecutive horizon")
        lo,hi=wilson(up,n)
        def pct(x):return round(float(x),4) if x is not None else None
        def projected(x):return round(baseline*(1+float(x)/100),2) if x is not None else None
        days.append({
            "after_trading_sessions":h,"eligible_examples":total,
            "observed_examples":n,"unmatured_examples":unmatured,
            "missing_quote_examples":missing,
            "up_count":up,"down_count":down,"flat_count":flat,
            "up_fraction_pct":round(up*100/n,3) if n else None,
            "down_fraction_pct":round(down*100/n,3) if n else None,
            "up_wilson_95_reference_pct":[lo,hi],
            "historical_mean_return_pct":pct(mean),
            "historical_median_return_pct":pct(median),
            "historical_p25_return_pct":pct(q25),
            "historical_p75_return_pct":pct(q75),
            "scenario_mean_yen":projected(mean),
            "scenario_median_yen":projected(median),
            "scenario_p25_yen":projected(q25),
            "scenario_p75_yen":projected(q75),
            "sample_status":"INSUFFICIENT" if n<100 else "HISTORICAL_ONLY",
        })
    return {
        "source":"Neon private daily_bar, aggregated joint historical patterns",
        "pattern_codes":patterns,"as_of":as_of,"historical_start":start,
        "historical_last_date":source_end,"reference_close_yen":baseline,
        "status":"PROVISIONAL_NOT_A_CALIBRATED_FORECAST",
        "observed_price_basis":"adjusted_close at end of each horizon vs pattern-date adjusted_close",
        "reference_price_method":"current_close times historical percentiles (not point-price forecast)",
        "sample_method":"at most one match per 30-global-session bucket per ticker",
        "limitations":[
            "Dates with no recorded future quote are NOT assumed to have risen or fallen.",
            "Only partial JPX listing-risk events are covered, and adjusted-close corporate actions are not fully audited.",
            "Similar-price patterns do not demonstrate calibrated forward price prediction or investment returns.",
            "One observation per fixed 30-session bucket is approximate de-overlap, not strict independence.",
            "No actual market/broker execution, fees, taxes, or bid-ask spread are modeled.",
            "Present-day pattern needs 21 correctly ordered current trading-day prices; old Neon quotes are stale."],
        "days":days}

def execute(conn,patterns,baseline,as_of,history_start,holdout_start):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trading_date) FROM daily_bar WHERE trading_date<=%s",
                    (as_of,))
        latest=cur.fetchone()[0]
        if latest is None:raise ValueError("No source history")
        latest=latest.isoformat()
        sql=build_sql(patterns)
        cur.execute(sql,(history_start,latest,history_start,latest,holdout_start))
        result=cur.fetchall()
    return summarize(result,choose_patterns(patterns),baseline,as_of,
                     holdout_start,latest)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--as-of",required=True,help="Current reference bar date")
    p.add_argument("--symbol",required=True,help="Security code, for labeling and JPX risk control")
    p.add_argument("--bars-json",help="21 private chronologically sorted daily bars for automatic detection")
    p.add_argument("--patterns",help="Comma-delimited codes when supplied externally")
    p.add_argument("--base-price",type=float,help="Known as-of adjusted close with --patterns")
    p.add_argument("--history-start",default="2025-12-01")
    p.add_argument("--holdout-start",default="2026-02-02")
    p.add_argument("--out",default="private-joint-pattern-forecast.json")
    args=p.parse_args()
    code=args.symbol.strip()
    if len(code)==4 and code.isdigit():code+="0"
    if not (code.isdigit() and len(code)==5):
        raise SystemExit("Invalid security code")
    date.fromisoformat(args.as_of)
    if risk_as_of_close(code,args.as_of):
        raise SystemExit("Official JPX risk event: refusing to publish a trading-style scenario")
    if args.bars_json:
        bars=json.loads(Path(args.bars_json).read_text(encoding="utf8"))
        if isinstance(bars,dict):bars=bars["bars"]
        tags,baseline=detect_recent(bars,args.as_of)
    else:
        if not args.patterns or args.base_price is None:
            raise SystemExit("Provide --bars-json or BOTH --patterns and --base-price")
        tags=choose_patterns(args.patterns.split(","))
        baseline=args.base_price
    if not tags:
        raise SystemExit("No registered specific patterns detected; BASE-only forecast is not informative")
    if args.as_of<=args.holdout_start:
        raise SystemExit("As-of date must be after holdout_start")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Install psycopg[binary] locally") from exc
    url=os.environ.get("DATABASE_URL")
    if not url:raise SystemExit("Missing DATABASE_URL")
    with psycopg.connect(url,sslmode="require") as conn:
        result=execute(conn,tags,baseline,args.as_of,
                       args.history_start,args.holdout_start)
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    chosen={d["after_trading_sessions"]:d for d in result["days"]}
    print(json.dumps({"symbol":code,"as_of":args.as_of,
       "joint_patterns":tags,"status":result["status"],"source_end":result["historical_last_date"],
       "summary":{str(h):{"up_pct":chosen[h]["up_fraction_pct"],
                           "median_yen":chosen[h]["scenario_median_yen"],
                           "samples":chosen[h]["observed_examples"]}
                  for h in (1,2,3,5,10,20,30)}},ensure_ascii=False))

if __name__=="__main__":main()
