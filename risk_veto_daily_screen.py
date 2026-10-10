#!/usr/bin/env python3
"""Research-only veto screening: exclude verified historically risky patterns.

No negative-pattern match is NOT evidence of safety. All output remains a
WATCHLIST, never an automated order or BUY authorization.
"""
import argparse
import json
import math
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

from downside_pattern_research import CATALOG, detect
from jpx_market_risk import risk_as_of_close

MODEL="risk-veto-v1"
HORIZON=20
# Conservatively predeclared multiple-test guard, not fitted to outcomes.
Z=3.9
TRAIN_MIN=500
HOLDOUT_MIN=250
UNIQUE_MIN=100
MAX_MISSING_RATE=.03
MIN_EXCESS_PCT=5.0
METRICS=(("touch_loss5_pct","path_complete_count"),
         ("close_loss5_pct","observed_count"),
         ("down_pct","observed_count"))

def wilson(success,total,z=Z):
    if total<=0:return (None,None)
    p=success/total; den=1+z*z/total
    midpoint=(p+z*z/(2*total))/den
    spread=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return (100*max(0,midpoint-spread),100*min(1,midpoint+spread))

def evidence(row,metric,denom_field,min_count):
    if row is None:return False
    n=int(row.get(denom_field) or 0)
    total=int(row.get("total_count") or 0)
    missing=int(row.get("missing_count") or 0)
    if n<min_count or int(row.get("unique_symbols") or 0)<UNIQUE_MIN:
        return False
    if not total or missing/total>MAX_MISSING_RATE:return False
    return row.get(metric) is not None

def select_veto_patterns(stat_rows, model_validation_status, coverage):
    """TRAIN significance selection, HOLDOUT independent confirmation.

    Confirmatory holdout is checked without choosing a new threshold using it.
    This is still research: no post-selection combined-cohort false-negative
    calibration, corporate-action audit or live data coverage.
    """
    if model_validation_status!="NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED":
        return {"rules":[],"state":"INCOMPATIBLE_MODEL"}
    if coverage!="JPX_LISTING_RISK_INCOMPLETE":
        return {"rules":[],"state":"INCOMPATIBLE_COVERAGE"}
    by={(r["pattern_code"],r["segment"]):r for r in stat_rows
        if int(r["horizon"])==HORIZON}
    base_train=by.get(("BASE","train"))
    base_holdout=by.get(("BASE","holdout"))
    if not base_train or not base_holdout:
        return {"rules":[],"state":"BASELINE_UNAVAILABLE"}
    rules=[]
    for code,(family,label) in CATALOG.items():
        if code=="BASE":continue
        train=by.get((code,"train")); holdout=by.get((code,"holdout"))
        for metric,denom in METRICS:
            if not all((
                evidence(train,metric,denom,TRAIN_MIN),
                evidence(base_train,metric,denom,TRAIN_MIN),
                evidence(holdout,metric,denom,HOLDOUT_MIN),
                evidence(base_holdout,metric,denom,HOLDOUT_MIN),
            )):continue
            a=int(train[denom]);b=int(base_train[denom])
            # The rates are rounded percentages. Their uncertainty is still
            # conservatively checked with extreme (Z=3.9) Wilson bounds.
            score=float(train[metric]);benchmark=float(base_train[metric])
            wins=round(a*score/100);bwins=round(b*benchmark/100)
            low,_=wilson(wins,a)
            _,upper=wilson(bwins,b)
            h_score=float(holdout[metric])
            h_benchmark=float(base_holdout[metric])
            if low is not None and low>upper and score>=benchmark+MIN_EXCESS_PCT \
                    and h_score>=h_benchmark+2.0:
                rules.append({
                    "code":code,"family":family,"name":label,"metric":metric,
                    "train_risk_pct":round(score,2),
                    "train_reference_pct":round(benchmark,2),
                    "holdout_risk_pct":round(h_score,2),
                    "holdout_reference_pct":round(h_benchmark,2),
                    "train_samples":a,"holdout_samples":int(holdout[denom]),
                })
                break
    return {"state":"CONDITIONAL_RISKS_FOUND" if rules else "NO_VALIDATED_VETO_RULES",
            "rules":sorted(rules,key=lambda r:(-r["train_risk_pct"]+r["train_reference_pct"],r["code"])),
            "limitations":"Holdout confirms marginal patterns only; no proof that their union reliably excludes future losing stocks."}

def verify_window(bars,required_days):
    if len(required_days)!=21 or len(bars)!=21:return False
    if [r["day"] for r in bars]!=required_days:return False
    return True

def judge_symbol(symbol,bars,required_days,rule_result):
    """No forced BUY: all unknowns and insufficient data fail closed."""
    day=required_days[-1]
    if risk_as_of_close(symbol,day):
        return {"symbol":symbol,"status":"EXCLUDE_KNOWN_JPX_WARNING",
                "veto":[],"observed_patterns":[]}
    if not verify_window(bars,required_days):
        return {"symbol":symbol,"status":"UNKNOWN_MISSING_MARKET_DAYS",
                "veto":[],"observed_patterns":[]}
    # If candle OHLC is missing, we cannot clear all negative candlestick rules.
    # This intentionally rejects even when close-based conditions are available.
    def complete(bar):
        for col in ("adjusted_close","open_price","close_price",
                    "high_price","low_price","volume"):
            try:
                val=float(bar.get(col))
                if not math.isfinite(val):return False
                if col!="volume" and val<=0:return False
                if col=="volume" and val<=0:return False
            except (ValueError,TypeError):
                return False
        return (float(bar["low_price"])<=
                min(float(bar["open_price"]),float(bar["close_price"]))<=
                max(float(bar["open_price"]),float(bar["close_price"]))<=
                float(bar["high_price"]))
    if not all(complete(r) for r in bars):
        return {"symbol":symbol,"status":"UNKNOWN_INVALID_CANDLES",
                "veto":[],"observed_patterns":[]}
    if not all(r.get("adjusted_close") is not None and
               r.get("volume") is not None for r in bars):
        return {"symbol":symbol,"status":"UNKNOWN_INCOMPLETE_PRICES",
                "veto":[],"observed_patterns":[]}
    tags=detect(bars)
    if not tags:
        return {"symbol":symbol,"status":"UNKNOWN_INSUFFICIENT_HISTORY",
                "veto":[],"observed_patterns":[]}
    if not rule_result["rules"]:
        return {"symbol":symbol,"status":"UNKNOWN_NO_VERIFIED_NEGATIVE_RULES",
                "veto":[],"observed_patterns":sorted(tags)}
    veto=sorted(set(tags)&{x["code"] for x in rule_result["rules"]})
    return {"symbol":symbol,
            "status":"EXCLUDE_DOWNSIDE_PATTERN" if veto
                 else "NO_VETO_MATCH_RESEARCH_ONLY",
            "veto":veto,"observed_patterns":sorted(tags)}

def freshness(source_day,today,max_age_days=4):
    age=(date.fromisoformat(today)-date.fromisoformat(source_day)).days
    return age>=0 and age<=max_age_days

def build_shortlist(day_rows,calendar,rule_result,today,strict_coverage=True):
    """Build daily candidate audit, fail-closed when stale or unsafe.

    Even today's high-quality data cannot authorize BUY while complete JPX
    risk and dividend/split audit are missing.
    """
    if not calendar:return {"state":"NO_MARKET_DATA","rows":[]}
    last=calendar[-1]
    if not freshness(last,today):
        return {"state":"STALE_DATA_NO_SCREEN","as_of":last,"rows":[],
                "ready_to_buy":0}
    required=calendar[-21:]
    if len(required)<21:
        return {"state":"INSUFFICIENT_MARKET_HISTORY","as_of":last,
                "rows":[],"ready_to_buy":0}
    listed=[]
    for symbol,bars in sorted(day_rows.items()):
        entry=judge_symbol(symbol,bars,required,rule_result)
        # Delisting status registry covers only a few symbols. We must not
        # mark any candidate as cleared for real-market trading.
        entry["execution_approval"]="NOT_APPROVED"
        if entry["status"]=="NO_VETO_MATCH_RESEARCH_ONLY":
            entry["reason"]="No validated downside veto matches, but loss remains possible"
        listed.append(entry)
    counts=defaultdict(int)
    for entry in listed:counts[entry["status"]]+=1
    return {
        "state":"RESEARCH_WATCHLIST_ONLY" if rule_result["rules"]
                else "NO_VERIFIED_RULES_NO_SCREEN",
        "as_of":last,"today":today,"rule_count":len(rule_result["rules"]),
        "market_status_audit":"INCOMPLETE","corporate_action_audit":"INCOMPLETE",
        "rows":listed,"counts":dict(counts),"ready_to_buy":0,
        "research_candidates":counts.get("NO_VETO_MATCH_RESEARCH_ONLY",0),
        "warning":"No matches is NOT proof of no downside risk; never execute trades automatically."}

def retrieve_rule_stats(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT run_key,validation_status,source_coverage
          FROM downside_pattern_run_v2
          WHERE model_version='downside-conditions-v2'
          ORDER BY calculated_at DESC LIMIT 1""")
        run=cur.fetchone()
        if run is None:raise ValueError("No completed downside research run")
        cur.execute("""SELECT pattern_code,segment,horizon,
          unique_symbols,total_count,observed_count,missing_count,
          path_complete_count,down_pct,close_loss5_pct,touch_loss5_pct
          FROM downside_pattern_stat_v2 WHERE run_key=%s AND horizon=%s""",
          (run[0],HORIZON))
        columns=[x.name for x in cur.description]
        rows=[dict(zip(columns,r)) for r in cur.fetchall()]
    result=select_veto_patterns(rows,run[1],run[2])
    result["source_run_key"]=run[0]
    return result

def primary_gate_verdict(rows,as_of):
    """Require both daily and 30-session-spaced historical improvement.

    If any evidence is stale, absent, inconclusive or negative, do not
    produce cleared research candidates. Even an improvement is NOT proof of
    future safety, and never grants brokerage approval.
    """
    by={sample:(verdict,source_day) for sample,verdict,source_day in rows}
    if set(by)!= {"daily","spaced30"}:
        return "PRIMARY_RISK_AUDIT_MISSING_NO_SCREEN"
    if any(source_day!=as_of for verdict,source_day in by.values()):
        return "PRIMARY_RISK_AUDIT_STALE_NO_SCREEN"
    if any(verdict!="IMPROVED_HISTORICALLY_NOT_PROSPECTIVELY_VALIDATED"
           for verdict,source_day in by.values()):
        return "PRIMARY_LOSS_RATE_FAILED_NO_SCREEN"
    return "PRIMARY_RESEARCH_IMPROVEMENT_ONLY"

def retrieve_primary_gate(conn,source_run_key,as_of):
    """Use the latest persisted audit for the identical source model run."""
    with conn.cursor() as cur:
        cur.execute("""SELECT e.sampling,e.primary_objective_result,
                              u.latest_source_day
                       FROM risk_veto_union_effectiveness_20day e
                       JOIN risk_veto_union_run u USING(run_key)
                       WHERE u.run_key=(
                         SELECT run_key FROM risk_veto_union_run
                         WHERE source_run_key=%s ORDER BY created_at DESC LIMIT 1
                       )""",(source_run_key,))
        rows=[(sample,verdict,day.isoformat()) for sample,verdict,day in cur]
    return primary_gate_verdict(rows,as_of)

def retrieve_current(conn):
    from split_adjustment_guard import inspect_guard
    blocked, _ = inspect_guard(conn)
    with conn.cursor() as cur:
        cur.execute("""SELECT trading_date FROM
          (SELECT DISTINCT trading_date FROM daily_bar
             ORDER BY trading_date DESC LIMIT 21) last21
          ORDER BY trading_date""")
        days=[r[0].isoformat() for r in cur.fetchall()]
    if len(days)<21:return days,{}
    with conn.cursor(name="risk_veto_last21") as cur:
        cur.itersize=5000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,
          open_price,high_price,low_price,close_price,volume
          FROM daily_bar WHERE trading_date >=%s AND trading_date <=%s
          ORDER BY security_code,trading_date""",(days[0],days[-1]))
        tickers=defaultdict(list)
        for code,day,adj,op,hi,lo,close,vol in cur:
            if code in blocked:
                continue
            tickers[code].append({
                "day":day.isoformat(),
                "adjusted_close":float(adj) if adj is not None else None,
                "open_price":float(op) if op is not None else None,
                "high_price":float(hi) if hi is not None else None,
                "low_price":float(lo) if lo is not None else None,
                "close_price":float(close) if close is not None else None,
                "volume":float(vol) if vol is not None else None})
    return days,tickers

def save(conn,snapshot):
    with conn.transaction():
        with conn.cursor() as cur:
            text_sql=Path("sql/009_risk_veto_watchlist.sql").read_text(encoding="utf8")
            for statement in text_sql.split(";"):
                if statement.strip():cur.execute(statement)
            cur.execute("""INSERT INTO risk_veto_scan_run
                (as_of,scan_state,rule_count,screened_count,watch_count,ready_to_buy,
                 market_status_audit,corporate_action_audit,scanned_at)
                VALUES (%s,%s,%s,%s,%s,0,'INCOMPLETE','INCOMPLETE',NOW())
                ON CONFLICT(as_of) DO UPDATE SET
                 scan_state=EXCLUDED.scan_state,rule_count=EXCLUDED.rule_count,
                 screened_count=EXCLUDED.screened_count,watch_count=EXCLUDED.watch_count,
                 ready_to_buy=0,scanned_at=NOW()""",
                 (snapshot.get("as_of",date.today().isoformat()),snapshot["state"],
                  snapshot.get("rule_count",0),len(snapshot.get("rows",[])),
                  snapshot.get("research_candidates",0)))
            cur.executemany("""INSERT INTO risk_veto_symbol_scan
                (as_of,security_code,status,matched_veto,observed_patterns,approval)
                VALUES (%s,%s,%s,%s,%s,'NOT_APPROVED')
                ON CONFLICT(as_of,security_code) DO UPDATE SET
                status=EXCLUDED.status,matched_veto=EXCLUDED.matched_veto,
                observed_patterns=EXCLUDED.observed_patterns,approval='NOT_APPROVED'""",
                [(snapshot["as_of"],r["symbol"],r["status"],r["veto"],r["observed_patterns"])
                for r in snapshot.get("rows",[])])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--today",default=date.today().isoformat())
    p.add_argument("--write-db",action="store_true")
    p.add_argument("--out",help="Optional PRIVATE JSON file")
    args=p.parse_args()
    import psycopg
    url=os.environ.get("DATABASE_URL")
    if not url:raise SystemExit("Missing DATABASE_URL")
    with psycopg.connect(url,sslmode="require") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(trading_date) FROM daily_bar")
            latest=cur.fetchone()[0]
        if latest is None:raise SystemExit("Empty market database")
        last=latest.isoformat()
        if not freshness(last,args.today):
            snapshot={"state":"STALE_DATA_NO_SCREEN","as_of":last,
                      "today":args.today,"rows":[],"ready_to_buy":0}
        else:
            rules=retrieve_rule_stats(conn)
            primary_gate=retrieve_primary_gate(conn,rules["source_run_key"],last)
            if primary_gate!="PRIMARY_RESEARCH_IMPROVEMENT_ONLY":
                snapshot={"state":primary_gate,"as_of":last,
                          "today":args.today,"rows":[],"ready_to_buy":0,
                          "rule_count":len(rules["rules"]),
                          "research_candidates":0}
            else:
                calendar,rows=retrieve_current(conn)
                snapshot=build_shortlist(rows,calendar,rules,args.today)
        if args.write_db:save(conn,snapshot)
    if args.out:
        Path(args.out).write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),
                                  encoding="utf8")
    print(json.dumps({"state":snapshot["state"],"source_day":snapshot.get("as_of"),
        "selected_bad_rules":snapshot.get("rule_count",0),
        "research_candidates":snapshot.get("research_candidates",0),
        "ready_to_buy":0,"stored":args.write_db},ensure_ascii=False))
if __name__=="__main__":main()
