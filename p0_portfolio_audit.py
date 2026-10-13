#!/usr/bin/env python3
"""Aggregate-only reconciliation of a paper portfolio against private Neon rows.

Never print tickers, licensed prices, position details, or DATABASE_URL.
An adjustment factor is NOT a verified corporate action.
"""
import argparse
import json
import os
from datetime import date

def exposure_windows(events, held, final_day):
    """Derive periods of market exposure from actual filled paper trades."""
    active = {}
    intervals = []
    for event in events:
        side = event.get("side")
        if side not in ("BUY", "SELL") or "qty" not in event:
            continue  # Includes NO_OPEN audit entries and corporate actions.
        code, day = event["code"], event["date"]
        date.fromisoformat(day)
        if side == "BUY":
            if code in active:
                raise ValueError("Repeated BUY for already-held security")
            active[code] = day
        else:
            if code not in active:
                raise ValueError("SELL without matching earlier BUY")
            intervals.append((code, active.pop(code), day))
    if set(active) != set(held):
        raise ValueError("Final holdings do not match executed trade ledger")
    intervals.extend((code, entry, final_day) for code, entry in active.items())
    return intervals

FINAL_SQL = """
WITH holdings AS (
  SELECT unnest(%s::text[]) AS code
)
SELECT
  COUNT(*) AS held,
  COUNT(*) FILTER (WHERE d.security_code IS NULL) AS absent_final_row,
  COUNT(*) FILTER (WHERE d.security_code IS NOT NULL
                   AND (d.close_price IS NULL OR d.close_price <= 0)) AS invalid_final_close,
  COUNT(*) FILTER (WHERE d.close_price > 0) AS valid_raw_final_close,
  COUNT(*) FILTER (WHERE d.close_price > 0 AND
                   (d.open_price IS NULL OR d.open_price <= 0
                    OR d.adjusted_close IS NULL OR d.adjusted_close <= 0
                    OR d.volume IS NULL)) AS valid_close_but_loader_excluded,
  COUNT(*) FILTER (WHERE prior.has_price IS NOT NULL) AS has_prior_valid_quote
FROM holdings h
LEFT JOIN daily_bar d
  ON d.security_code=h.code AND d.trading_date=%s::date
LEFT JOIN LATERAL (
  SELECT 1 AS has_price FROM daily_bar p
  WHERE p.security_code=h.code AND p.trading_date<%s::date
    AND p.close_price > 0
  LIMIT 1
) prior ON TRUE
"""
GAP_SQL = """
WITH params AS (SELECT %s::date AS final_day),
holdings AS (SELECT unnest(%s::text[]) AS code),
missing AS (
  SELECT h.code FROM holdings h CROSS JOIN params p
  LEFT JOIN daily_bar d
    ON d.security_code=h.code AND d.trading_date=p.final_day
  WHERE d.security_code IS NULL OR d.close_price IS NULL OR d.close_price<=0
)
SELECT
 COUNT(*) AS missing_final_holdings,
 COUNT(*) FILTER (WHERE q.last_valid_date IS NULL) AS no_prior_valid_close,
 COUNT(*) FILTER (WHERE p.final_day-q.last_valid_date BETWEEN 0 AND 7) AS prior_close_age_0_to_7_days,
 COUNT(*) FILTER (WHERE p.final_day-q.last_valid_date BETWEEN 8 AND 30) AS prior_close_age_8_to_30_days,
 COUNT(*) FILTER (WHERE p.final_day-q.last_valid_date > 30) AS prior_close_age_over_30_days,
 COUNT(*) FILTER (WHERE r.last_row_date > q.last_valid_date
                   OR (q.last_valid_date IS NULL AND r.last_row_date IS NOT NULL))
                   AS later_unpriced_rows_after_last_valid_close,
 MIN(p.final_day-q.last_valid_date) AS min_prior_close_age_days,
 MAX(p.final_day-q.last_valid_date) AS max_prior_close_age_days
FROM missing m CROSS JOIN params p
LEFT JOIN LATERAL (
  SELECT trading_date AS last_valid_date FROM daily_bar b
  WHERE b.security_code=m.code AND b.trading_date<p.final_day AND b.close_price>0
  ORDER BY b.trading_date DESC LIMIT 1
) q ON TRUE
LEFT JOIN LATERAL (
  SELECT trading_date AS last_row_date FROM daily_bar b
  WHERE b.security_code=m.code AND b.trading_date<p.final_day
  ORDER BY b.trading_date DESC LIMIT 1
) r ON TRUE
"""
EXPOSURE_SQL = """
WITH intervals AS (
  SELECT code,start_date,end_date
  FROM unnest(%s::text[],%s::date[],%s::date[])
       AS i(code,start_date,end_date)
)
SELECT
 COUNT(*) FILTER (WHERE b.adjustment_factor <> 1) AS unusual_factor_rows,
 COUNT(DISTINCT i.code) FILTER (WHERE b.adjustment_factor <> 1) AS exposed_symbols_with_factor,
 COUNT(*) FILTER (WHERE b.adjustment_factor IS NULL) AS unknown_factor_rows
FROM intervals i
JOIN daily_bar b ON b.security_code=i.code
    AND b.trading_date BETWEEN i.start_date AND i.end_date
"""

def summarize(result, final_stats, exposure_stats, windows, gap_stats=None):
    paper=result["paper_result"]
    diagnostics=paper["valuation_diagnostics"]
    stats={k:int(v or 0) for k,v in final_stats.items()}
    exposure={k:int(v or 0) for k,v in exposure_stats.items()}
    if stats["held"] != len(paper["held"]):
        raise AssertionError("Portfolio holdings count differs from DB lookup")
    missing=stats["absent_final_row"]+stats["invalid_final_close"]
    gap = {k:(int(v) if v is not None else None)
           for k,v in (gap_stats or {}).items()}
    if gap_stats:
        if gap["missing_final_holdings"] != missing:
            raise AssertionError("Final-price gap counts disagree")
        known_age = sum(gap[k] for k in (
            "prior_close_age_0_to_7_days",
            "prior_close_age_8_to_30_days",
            "prior_close_age_over_30_days"))
        if known_age + gap["no_prior_valid_close"] != missing:
            raise AssertionError("Last-quote age buckets do not reconcile")
    blockers = ["CORPORATE_ACTION_AND_DELISTING_EVIDENCE_UNVERIFIED"]
    if missing:
        blockers.append("HELD_FINAL_QUOTE_MISSING")
    if exposure["unusual_factor_rows"] or exposure["unknown_factor_rows"]:
        blockers.append("EXPOSURE_ADJUSTMENT_FACTORS_REQUIRE_REVIEW")
    return {
        "experiment":"PRIOR_SELECTED_RULE_REPLAY_UNVERIFIED",
        "last_date":result["data_last_date"],
        "paper_held_positions":len(paper["held"]),
        "source_absent_final_rows":stats["absent_final_row"],
        "source_invalid_final_close":stats["invalid_final_close"],
        "source_valid_raw_final_close":stats["valid_raw_final_close"],
        "source_valid_close_but_loader_excluded":stats["valid_close_but_loader_excluded"],
        "positions_with_prior_valid_quote":stats["has_prior_valid_quote"],
        "paper_held_without_final_close":diagnostics["held_positions_without_final_close"],
        "exposure_intervals":len(windows),
        "exposure_unusual_factor_rows":exposure["unusual_factor_rows"],
        "exposed_symbols_with_unusual_factor":exposure["exposed_symbols_with_factor"],
        "exposure_unknown_factor_rows":exposure["unknown_factor_rows"],
        "formal_final_equity_available":paper["final_equity"] is not None,
        "missing_final_holding_gap_provenance":gap if gap_stats else None,
        "blocking_reasons":blockers,
        "validation_status":"BLOCKED_EXTERNAL_DATA",
        "limitation":"An adjustment factor of 1 or absence of unusual factors cannot verify corporate actions or delisting. Prior prices are NOT final prices; no verified event registry or brokerage execution evidence."
    }

def audit(conn, result):
    if result.get("status")!="completed" or result.get("selection_provenance")!="EXTERNAL_PRIOR_RUN_NOT_RETRAINED":
        raise ValueError("Only the documented fixed-rule paper replay can be audited here")
    final_day=result["data_last_date"]
    date.fromisoformat(final_day)
    paper=result["paper_result"]
    held=paper["held"]
    windows=exposure_windows(paper["fills"],held,final_day)
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trading_date)::text AS last_day FROM daily_bar")
        if cur.fetchone()[0]!=final_day:
            raise ValueError("Database final session has changed; replay required")
        cur.execute(FINAL_SQL,(list(held),final_day,final_day))
        keys=[c.name for c in cur.description]
        final_stats=dict(zip(keys,cur.fetchone()))
        codes=[p[0] for p in windows]
        starts=[p[1] for p in windows]
        ends=[p[2] for p in windows]
        cur.execute(EXPOSURE_SQL,(codes,starts,ends))
        keys=[c.name for c in cur.description]
        exposure_stats=dict(zip(keys,cur.fetchone()))
        cur.execute(GAP_SQL,(final_day,list(held)))
        keys=[c.name for c in cur.description]
        gap_stats=dict(zip(keys,cur.fetchone()))
    return summarize(result, final_stats, exposure_stats, windows, gap_stats)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("result",help="Private paper replay JSON in Actions runner")
    args=parser.parse_args()
    with open(args.result,encoding="utf-8") as fh:
        paper=json.load(fh)
    url=os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL unavailable")
    import psycopg
    with psycopg.connect(url,sslmode="require") as conn:
        report=audit(conn,paper)
    print("P0_SOURCE_AUDIT "+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
