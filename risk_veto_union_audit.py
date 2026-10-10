#!/usr/bin/env python3
"""Retrospective union-veto audit. No trading approval or price publication.

Rule selection uses ONLY the TRAIN segment of an existing V2 research run.
The later test segment is never read during rule selection. Because this
experiment was conceived after prior exploration of the test era, its results
are retrospective research, NOT a pristine prospective validation.
"""
import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

from downside_pattern_research import CATALOG, adjusted, detect
from split_adjustment_guard import inspect_guard
from jpx_market_risk import risk_as_of_close
from risk_veto_daily_screen import (
    METRICS, TRAIN_MIN, UNIQUE_MIN, MAX_MISSING_RATE,
    MIN_EXCESS_PCT, wilson,
)

HORIZONS = range(1, 31)
TEST_START = "2026-02-02"
FEE_PER_SIDE = 0.001
STATUS = "RETROSPECTIVE_TEST_NOT_PROSPECTIVE_CORPORATE_ACTIONS_UNVERIFIED"


def train_only_rules(rows):
    """Select on historical TRAIN metrics without ever reading holdout rows."""
    by = {r["pattern_code"]: r for r in rows if r["segment"] == "train"}
    base = by.get("BASE")
    if base is None:
        raise ValueError("Missing TRAIN baseline")
    rules = []
    for code, (family, label) in CATALOG.items():
        if code == "BASE" or code not in by:
            continue
        r = by[code]
        for metric, denominator in METRICS:
            n = int(r.get(denominator) or 0)
            bn = int(base.get(denominator) or 0)
            total = int(r.get("total_count") or 0)
            missing = int(r.get("missing_count") or 0)
            rate = r.get(metric)
            reference = base.get(metric)
            if (n < TRAIN_MIN or bn < TRAIN_MIN
                    or int(r.get("unique_symbols") or 0) < UNIQUE_MIN
                    or not total or missing / total > MAX_MISSING_RATE
                    or rate is None or reference is None):
                continue
            rate, reference = float(rate), float(reference)
            low, _ = wilson(round(n * rate / 100), n)
            _, high = wilson(round(bn * reference / 100), bn)
            if low > high and rate >= reference + MIN_EXCESS_PCT:
                rules.append({
                    "code": code, "family": family, "name": label,
                    "metric": metric, "train_pct": rate,
                    "train_baseline_pct": reference, "train_count": n,
                })
                break
    return sorted(rules, key=lambda v: v["code"])


def signal_status(code, t, obs, normalized, days, veto_codes):
    """A false match is NEVER inferred from an incomplete chart."""
    if t < 20 or risk_as_of_close(code, days[t]):
        return "UNKNOWN_JPX_OR_HISTORY", ()
    window = [obs.get(i) for i in range(t - 20, t + 1)]
    if any(bar is None for bar in window):
        return "UNKNOWN_MISSING_CHART_DAYS", ()
    for i in range(t - 20, t + 1):
        bar = normalized.get(i)
        if (bar is None or bar[1] <= 0
                or any(x is None or not math.isfinite(x) for x in bar[2:])):
            return "UNKNOWN_INVALID_OHLCV", ()
    matched = tuple(sorted(detect(window) & veto_codes))
    return ("EXCLUDED" if matched else "SURVIVOR"), matched


def net_pct(entry_open, future_close, fee=FEE_PER_SIDE):
    if entry_open is None or future_close is None or entry_open <= 0:
        return None
    return 100 * (future_close * (1 - fee) / (entry_open * (1 + fee)) - 1)


def future_outcomes(t, normalized, horizons=HORIZONS, fee=FEE_PER_SIDE):
    """Buy at next observed global-session adjusted OPEN, mark subsequent closes.

    Missing entry, high/low path or terminal close is UNKNOWN, not a gain.
    Intraday low thresholds indicate exposures, not executable stop fills.
    """
    first = normalized.get(t + 1)
    # An OPEN without positive traded volume cannot be assumed to fill.
    entry = first[2] if first is not None and first[1] > 0 else None
    low = math.inf
    path_ok = True
    for h in horizons:
        row = normalized.get(t + h)
        if row is None or row[4] is None or row[1] <= 0:
            path_ok = False
        else:
            low = min(low, row[4])
        if row is None or row[1] <= 0 or entry is None or row[0] is None:
            yield h, None
            continue
        net = net_pct(entry, row[0], fee)
        if net is None:
            yield h, None
            continue
        adverse = net_pct(entry, low, fee) if path_ok else None
        yield h, {"net": net, "path": adverse,
                  "close3": net <= -3, "close5": net <= -5,
                  "close10": net <= -10}


def fresh_bucket():
    return {"events": 0, "observed": 0, "missing": 0,
            "losses": 0, "up": 0, "flat": 0,
            "close3": 0, "close5": 0, "close10": 0,
            "path_complete": 0, "path_unknown": 0,
            "touch3": 0, "touch5": 0, "touch10": 0,
            "net_sum": 0.0}


def add_bucket(bucket, event):
    bucket["events"] += 1
    if event is None:
        bucket["missing"] += 1
        return
    bucket["observed"] += 1
    net = event["net"]
    bucket["net_sum"] += net
    bucket["losses"] += net < 0
    bucket["up"] += net > 0
    bucket["flat"] += net == 0
    for threshold in (3, 5, 10):
        bucket[f"close{threshold}"] += event[f"close{threshold}"]
    if event["path"] is None:
        bucket["path_unknown"] += 1
    else:
        bucket["path_complete"] += 1
        for threshold in (3, 5, 10):
            bucket[f"touch{threshold}"] += event["path"] <= -threshold


def evaluate_one(code, obs, days, first_t, final_t, veto_codes, accum,
                 rule_accum, snapshot, snapshot_t):
    normalized = {i: adjusted(bar) for i, bar in obs.items()}
    last_spaced = -9999
    for t in range(first_t, final_t + 1):
        status, matched = signal_status(code, t, obs, normalized, days, veto_codes)
        if t == snapshot_t:
            snapshot.append((days[t], code, status, list(matched)))
        if status not in ("EXCLUDED", "SURVIVOR"):
            accum["unknown_signals"][status] += 1
            continue
        spaced = t - last_spaced >= 30
        if spaced:
            last_spaced = t
        for h, outcome in future_outcomes(t, normalized):
            cohorts = [("daily", "ALL"), ("daily", status)]
            if spaced:
                cohorts += [("spaced30", "ALL"), ("spaced30", status)]
            for key in cohorts:
                add_bucket(accum["cohorts"][(key[0], key[1], h)], outcome)
            if h == 20 and matched:
                for pattern in matched:
                    add_bucket(rule_accum[pattern], outcome)


def evaluate_rows(by_code, days, veto_codes, test_start=TEST_START):
    first_t = next((i for i, d in enumerate(days) if d >= test_start), None)
    final_t = len(days) - 31  # All 30 forward sessions must exist.
    if first_t is None or first_t > final_t:
        raise ValueError("No fully matured test signals")
    buckets = defaultdict(fresh_bucket)
    accum = {"cohorts": buckets, "unknown_signals": defaultdict(int)}
    rule_accum = defaultdict(fresh_bucket)
    snapshot = []
    for code, obs in by_code.items():
        evaluate_one(code, obs, days, first_t, final_t, veto_codes,
                     accum, rule_accum, snapshot, final_t)
    return {"cohorts": dict(buckets),
            "unknown_signals": dict(accum["unknown_signals"]),
            "rule_performance": dict(rule_accum),
            "snapshot": snapshot,
            "signal_start": days[first_t],
            "signal_end": days[final_t],
            "last_data_day": days[-1]}


def read_train_rules(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT run_key,holdout_start,validation_status,source_coverage
                       FROM downside_pattern_run_v2
                       WHERE model_version='downside-conditions-v2'
                       ORDER BY calculated_at DESC LIMIT 1""")
        meta = cur.fetchone()
        if not meta:
            raise ValueError("V2 research run not found")
        run_key, holdout_start, validation, coverage = meta
        if (validation != "NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED"
                or coverage != "JPX_LISTING_RISK_INCOMPLETE"):
            raise ValueError("Unrecognized research run status")
        cur.execute("""SELECT pattern_code,segment,horizon,unique_symbols,
                              total_count,observed_count,missing_count,
                              path_complete_count,down_pct,close_loss5_pct,
                              touch_loss5_pct
                       FROM downside_pattern_stat_v2
                       WHERE run_key=%s AND segment='train' AND horizon=20""",
                    (run_key,))
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur]
    return run_key, holdout_start.isoformat(), train_only_rules(rows)


def from_neon(conn, test_start=TEST_START):
    blocked, split_summary = inspect_guard(conn)
    source, holdout_start, rules = read_train_rules(conn)
    if test_start < holdout_start:
        raise ValueError("Test would overlap the model TRAIN period")
    if not rules:
        raise ValueError("No TRAIN-only veto conditions. Fail closed.")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT trading_date FROM daily_bar ORDER BY trading_date")
        days = [r[0].isoformat() for r in cur]
    index = {d: i for i, d in enumerate(days)}
    first_t = next((i for i, d in enumerate(days) if d >= test_start), None)
    if first_t is None or first_t > len(days) - 31:
        raise ValueError("No completed 30-day test horizon")
    accum = {"cohorts": defaultdict(fresh_bucket),
             "unknown_signals": defaultdict(int)}
    perf = defaultdict(fresh_bucket)
    snapshot = []
    active, obs = None, {}
    scanned = 0
    veto_codes = {r["code"] for r in rules}
    with conn.cursor(name="risk_veto_oos_stream") as cur:
        cur.itersize = 15000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,
                              open_price,high_price,low_price,close_price,volume
                       FROM daily_bar ORDER BY security_code,trading_date""")
        for code, day, adj, op, hi, lo, close, vol in cur:
            if code in blocked:
                continue
            if active is not None and code != active:
                evaluate_one(active, obs, days, first_t, len(days)-31,
                             veto_codes, accum, perf, snapshot, len(days)-31)
                scanned += 1
                obs = {}
            active = code
            obs[index[day.isoformat()]] = {
                "adjusted_close": float(adj) if adj is not None else None,
                "open_price": float(op) if op is not None else None,
                "high_price": float(hi) if hi is not None else None,
                "low_price": float(lo) if lo is not None else None,
                "close_price": float(close) if close is not None else None,
                "volume": float(vol) if vol is not None else None}
        if active is not None:
            evaluate_one(active, obs, days, first_t, len(days)-31,
                         veto_codes, accum, perf, snapshot, len(days)-31)
            scanned += 1
    return {
        "source_run_key": source, "rules": rules, "scanned_symbols": scanned,
        "corporate_action_guard": split_summary,
        "signal_start": days[first_t], "signal_end": days[-31],
        "last_data_day": days[-1], "cohorts": dict(accum["cohorts"]),
        "unknown_signals": dict(accum["unknown_signals"]),
        "rule_performance": dict(perf), "snapshot": snapshot,
    }


def store(conn, result, commit_sha):
    identity = "|".join((result["source_run_key"], commit_sha,
                         result["signal_start"], result["signal_end"],
                         str(FEE_PER_SIDE),
                         result["corporate_action_guard"]["guard_version"]))
    run_key = hashlib.sha256(identity.encode()).hexdigest()[:32]
    statements = Path("sql/010_risk_veto_union_audit.sql").read_text(
        encoding="utf8").split(";")
    with conn.transaction():
        with conn.cursor() as cur:
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
            cur.execute("""INSERT INTO risk_veto_union_run
             (run_key,source_run_key,commit_sha,signal_start,signal_end,
              latest_source_day,rule_count,scanned_symbols,status,fee_per_side)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
             ON CONFLICT (run_key) DO NOTHING""",
             (run_key, result["source_run_key"], commit_sha,
              result["signal_start"], result["signal_end"],
              result["last_data_day"], len(result["rules"]),
              result["scanned_symbols"], STATUS, FEE_PER_SIDE))
            cur.executemany("""INSERT INTO risk_veto_union_cohort
             (run_key,sampling,cohort,horizon,total,observed,missing,
              loss_count,up_count,flat_count,close_loss3_count,
              close_loss5_count,close_loss10_count,path_complete_count,
              path_unknown_count,touch_loss3_count,touch_loss5_count,
              touch_loss10_count,net_sum_pct)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
             ON CONFLICT DO NOTHING""",
             [(run_key, sampling, cohort, h,
               b["events"], b["observed"], b["missing"],
               b["losses"], b["up"], b["flat"], b["close3"], b["close5"],
               b["close10"], b["path_complete"], b["path_unknown"],
               b["touch3"], b["touch5"], b["touch10"], b["net_sum"])
              for (sampling, cohort, h), b in result["cohorts"].items()])
            cur.executemany("""INSERT INTO risk_veto_union_rule
             (run_key,pattern_code,metric,train_pct,train_baseline_pct,
              train_count,matched20_count,observed20_count,loss20_count)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
             ON CONFLICT DO NOTHING""",
             [(run_key, r["code"], r["metric"], r["train_pct"],
               r["train_baseline_pct"], r["train_count"],
               result["rule_performance"].get(r["code"], {}).get("events", 0),
               result["rule_performance"].get(r["code"], {}).get("observed", 0),
               result["rule_performance"].get(r["code"], {}).get("losses", 0))
              for r in result["rules"]])
            cur.executemany("""INSERT INTO risk_veto_union_snapshot
             (run_key,as_of,security_code,status,matched_veto)
             VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
             [(run_key, day, code, status, matched)
              for day, code, status, matched in result["snapshot"]])
    return run_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--test-start", default=TEST_START)
    ap.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", "manual"))
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Missing private DATABASE_URL")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], sslmode="require") as conn:
        result = from_neon(conn, args.test_start)
        key = store(conn, result, args.source_commit) if args.write_db else None
    def rate(bucket):
        return round(100 * bucket["losses"] / bucket["observed"], 3) if bucket["observed"] else None
    print(json.dumps({
        "state": STATUS, "test_start": result["signal_start"],
        "test_end": result["signal_end"], "last_source_day": result["last_data_day"],
        "trained_rule_count": len(result["rules"]),
        "source_run_key": result["source_run_key"],
        "corporate_action_guard": result["corporate_action_guard"],
        "snapshot_counts": dict(__import__("collections").Counter(x[2] for x in result["snapshot"])),
        "loss20_daily": {cohort: rate(result["cohorts"].get(("daily", cohort, 20), fresh_bucket()))
                         for cohort in ("ALL", "EXCLUDED", "SURVIVOR")},
        "run_key": key, "stored": bool(key),
        "approval": "NOT_APPROVED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
