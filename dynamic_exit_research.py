#!/usr/bin/env python3
"""Research-only adaptive 30-session exit study, point-in-time and cash-long.

Goal order: reduce probability of *any* after-fee loss, avoid worsening major
losses, and then increase average after-fee return. The predetermined exit
policies are selected using TRAIN_A and TRAIN_B only; HOLDOUT cannot select a
policy. Previously inspected 2026 data is retrospective, not prospective.
"""
import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from downside_pattern_research import adjusted
from risk_veto_union_audit import FEE_PER_SIDE, net_pct, read_train_rules, signal_status

STATUS = "RETROSPECTIVE_ADAPTIVE_EXIT_NOT_APPROVED"
MAX_HOLD = 30
TRAIN_SPLIT = "2025-07-01"
POLICIES_VERSION = "adaptive-eod-exits-v1"


@dataclass(frozen=True)
class Policy:
    name: str
    fixed_day: int = 30
    stop_close: float = 0.0
    target_close: float = 0.0
    trailing_close: float = 0.0
    pattern: str = ""

    def __post_init__(self):
        if not (1 <= self.fixed_day <= MAX_HOLD
                and all(0 <= x < 100 for x in (
                    self.stop_close, self.target_close, self.trailing_close))
                and self.pattern in ("", "TWO_RED", "DOWN3", "MA_BEAR")):
            raise ValueError("Unsupported exit policy")


POLICIES = (
    [Policy("HOLD30")]
    + [Policy(f"DAY{n:02d}", fixed_day=n) for n in (5, 10, 20)]
    + [Policy(f"STOP_CLOSE{n}", stop_close=n) for n in (1, 2, 3, 5)]
    + [Policy(f"TARGET_CLOSE{n}", target_close=n) for n in (2, 5, 10)]
    + [Policy(f"TRAIL_CLOSE{n}", trailing_close=n) for n in (2, 3, 5)]
    + [Policy(f"PATTERN_{p}", pattern=p) for p in ("TWO_RED", "DOWN3", "MA_BEAR")]
    + [Policy(f"STOP{s}_TARGET{t}", stop_close=s, target_close=t)
       for s in (2, 3, 5) for t in (3, 5)]
)
POLICY_BY_NAME = {p.name: p for p in POLICIES}
assert len(POLICY_BY_NAME) == len(POLICIES)


def valid_session(row, require_close=True):
    if row is None or row[1] <= 0 or row[2] is None:
        return False
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0
               for x in (row[0], row[2], row[3], row[4])):
        return False
    if row[4] > min(row[2], row[0]) or row[3] < max(row[2], row[0]):
        return False
    return True


def valid_open(row):
    """No day-30 high, low or closing mark can influence an OPEN exit."""
    return (row is not None and row[1] > 0 and row[2] is not None
            and isinstance(row[2], (int, float))
            and math.isfinite(row[2]) and row[2] > 0)


def replay_exit(t, normalized, policy, fee=FEE_PER_SIDE):
    """Enter next market OPEN; EOD exit signals fill *following* OPEN.

    For the 30th session, exit at the already-prescribed session-30 OPEN
    without seeing that day's close. Missing/suspended exit OPEN is UNKNOWN.
    No intraday stop execution is assumed: overnight gaps remain real losses.
    """
    first = normalized.get(t + 1)
    if not valid_session(first):
        return None
    entry = first[2]
    peak_close = entry
    previous = normalized.get(t)
    if previous is None or previous[0] is None:
        return None
    previous_close = previous[0]
    red_streak = 0
    pending = None
    for h in range(1, MAX_HOLD + 1):
        row = normalized.get(t + h)
        if pending or h == MAX_HOLD:
            if not valid_open(row):
                return None
            return {"net": net_pct(entry, row[2], fee), "day": h,
                    "reason": pending or "MAX_HOLD_OPEN",
                    "entry": entry, "exit": row[2]}
        if not valid_session(row):
            return None
        close = row[0]
        gross = (close / entry - 1) * 100
        peak_close = max(peak_close, close)
        red_streak = red_streak + 1 if close < previous_close else 0
        previous_close = close
        # All these observations are known only after session h has closed.
        if h >= policy.fixed_day:
            pending = "FIXED_DAY_CLOSE"
        elif policy.stop_close and gross <= -policy.stop_close:
            pending = "STOP_CLOSE"
        elif policy.target_close and gross >= policy.target_close:
            pending = "TARGET_CLOSE"
        elif (policy.trailing_close and peak_close > entry
              and 100 * (close / peak_close - 1) <= -policy.trailing_close):
            pending = "TRAIL_CLOSE"
        elif policy.pattern == "TWO_RED" and h >= 2 and red_streak >= 2:
            pending = "PATTERN_TWO_RED"
        elif policy.pattern == "DOWN3" and close / (normalized[t + h - 1][0]) <= .97:
            pending = "PATTERN_DOWN3"
        elif policy.pattern == "MA_BEAR":
            recent = [normalized.get(j) for j in range(t + h - 19, t + h + 1)]
            if any(x is None or x[0] is None or not math.isfinite(x[0])
                   or x[0] <= 0 for x in recent):
                return None
            if sum(x[0] for x in recent[-5:]) / 5 < sum(x[0] for x in recent) / 20:
                pending = "PATTERN_MA_BEAR"
    raise AssertionError("30-session exit unreachable")


def blank():
    return {"events": 0, "observed": 0, "unknown": 0,
            "loss": 0, "positive": 0, "flat": 0, "loss5": 0,
            "net_sum": 0.0, "paired": 0, "paired_wins": 0,
            "paired_harms": 0, "paired_candidate_loss5": 0,
            "paired_baseline_loss5": 0, "paired_delta_sum": 0.0}


def count(stats, candidate, baseline):
    stats["events"] += 1
    if candidate is None:
        stats["unknown"] += 1
    else:
        n = candidate["net"]
        stats["observed"] += 1
        stats["loss"] += n < 0
        stats["positive"] += n > 0
        stats["flat"] += n == 0
        stats["loss5"] += n <= -5
        stats["net_sum"] += n
    # Only paired, observed trades are admissible for training comparisons.
    if candidate is None or baseline is None:
        return
    a, b = candidate["net"], baseline["net"]
    stats["paired"] += 1
    stats["paired_wins"] += a >= 0 and b < 0
    stats["paired_harms"] += a < 0 and b >= 0
    stats["paired_candidate_loss5"] += a <= -5
    stats["paired_baseline_loss5"] += b <= -5
    stats["paired_delta_sum"] += a - b


def segment_ranges(days, train_end, train_split, holdout_start):
    if not (train_split < train_end < holdout_start):
        raise ValueError("Chronological training / holdout boundaries required")
    split = next((i for i, d in enumerate(days) if d >= train_split), None)
    end = next((i for i, d in enumerate(days) if d > train_end), len(days))
    start_test = next((i for i, d in enumerate(days) if d >= holdout_start), None)
    if split is None or start_test is None or end >= len(days):
        raise ValueError("Incomplete training or testing source data")
    result = (
        ("TRAIN_A", 20, split - MAX_HOLD - 1),
        ("TRAIN_B", split, end - MAX_HOLD - 1),
        ("HOLDOUT", start_test, len(days) - MAX_HOLD - 1),
    )
    if any(first > last or first < 20 for _, first, last in result):
        raise ValueError("Every segment needs 21 candles and 30 matured sessions")
    return result


def evaluate_one(code, obs, days, ranges, veto_codes, stats, exit_days, unknown):
    normalized = {i: adjusted(bar) for i, bar in obs.items()}
    for segment, first, last in ranges:
        previous_sample = -MAX_HOLD - 100
        for t in range(first, last + 1):
            if t - previous_sample < MAX_HOLD:
                continue
            status, _ = signal_status(code, t, obs, normalized, days, veto_codes)
            if status not in ("EXCLUDED", "SURVIVOR"):
                unknown[(segment, status)] += 1
                continue
            previous_sample = t
            baseline = replay_exit(t, normalized, POLICY_BY_NAME["HOLD30"])
            for policy in POLICIES:
                outcome = baseline if policy.name == "HOLD30" else replay_exit(
                    t, normalized, policy)
                for cohort in ("ALL", status):
                    key = segment, cohort, policy.name
                    count(stats[key], outcome, baseline)
                    if outcome is not None:
                        bucket = exit_days[key, outcome["day"]]
                        bucket["count"] += 1
                        bucket["loss"] += outcome["net"] < 0
                        bucket["net_sum"] += outcome["net"]


def analyze(by_code, days, train_end, holdout_start, veto_codes,
            train_split=TRAIN_SPLIT):
    ranges = segment_ranges(days, train_end, train_split, holdout_start)
    stats, exits = defaultdict(blank), defaultdict(
        lambda: {"count": 0, "loss": 0, "net_sum": 0.0})
    unknown = defaultdict(int)
    for code, obs in by_code.items():
        evaluate_one(code, obs, days, ranges, veto_codes, stats, exits, unknown)
    result = {"statistics": dict(stats), "exits": dict(exits),
              "unknown_signals": dict(unknown)}
    result["selection"] = choose_train_only(stats)
    return result


def choose_train_only(stats, minimum=400):
    """Predeclared conservative train-only policy selection.

    Requires BOTH chronological training subperiods to have a statistically
    positive paired ANY-loss improvement and no worsening of severe losses or
    mean return. Never inspect HOLDOUT to choose/change a candidate.
    """
    candidates = []
    for policy in POLICIES:
        if policy.name == "HOLD30":
            continue
        fold = []
        for segment in ("TRAIN_A", "TRAIN_B"):
            b = stats.get((segment, "SURVIVOR", policy.name), blank())
            n = b["paired"]
            if n < minimum or b["events"] == 0 or b["unknown"] / b["events"] > .05:
                break
            wins, harms = b["paired_wins"], b["paired_harms"]
            lb = (wins - harms - 1.96 * math.sqrt(wins + harms)) / n * 100
            return_delta = b["paired_delta_sum"] / n
            if (lb <= 0 or b["paired_candidate_loss5"] >
                    b["paired_baseline_loss5"] or return_delta < 0):
                break
            fold.append((lb, return_delta, n))
        if len(fold) == 2:
            candidates.append((min(x[0] for x in fold),
                               min(x[1] for x in fold), policy.name, fold))
    candidates.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return {
        "selected": candidates[0][2] if candidates else None,
        "state": "TRAIN_ONLY_RESEARCH_CANDIDATE" if candidates
                 else "NO_TRAIN_VALIDATED_EXIT_POLICY",
        "eligible_count": len(candidates),
        "best_lower_improvement_pp": round(candidates[0][0], 4) if candidates else None,
        "not_a_live_trade_approval": True,
    }


def from_neon(conn, train_split=TRAIN_SPLIT):
    source_run, holdout_start, rules = read_train_rules(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT train_end FROM downside_pattern_run_v2 WHERE run_key=%s",
                    (source_run,))
        train_end = cur.fetchone()[0].isoformat()
        cur.execute("SELECT DISTINCT trading_date FROM daily_bar ORDER BY trading_date")
        days = [v[0].isoformat() for v in cur]
    ranges = segment_ranges(days, train_end, train_split, holdout_start)
    indices = {d: i for i, d in enumerate(days)}
    stats, exits = defaultdict(blank), defaultdict(
        lambda: {"count": 0, "loss": 0, "net_sum": 0.0})
    unknown = defaultdict(int)
    current, obs, scanned = None, {}, 0
    veto = {x["code"] for x in rules}
    with conn.cursor(name="private_dynamic_exit_stream") as cur:
        cur.itersize = 15000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,
                       open_price,high_price,low_price,close_price,volume
                       FROM daily_bar ORDER BY security_code,trading_date""")
        for code, day, adj, op, hi, lo, close, vol in cur:
            if current is not None and current != code:
                evaluate_one(current, obs, days, ranges, veto, stats, exits, unknown)
                scanned += 1
                obs = {}
            current = code
            obs[indices[day.isoformat()]] = {
                "adjusted_close": float(adj) if adj is not None else None,
                "open_price": float(op) if op is not None else None,
                "high_price": float(hi) if hi is not None else None,
                "low_price": float(lo) if lo is not None else None,
                "close_price": float(close) if close is not None else None,
                "volume": float(vol) if vol is not None else None}
        if current is not None:
            evaluate_one(current, obs, days, ranges, veto, stats, exits, unknown)
            scanned += 1
    return {
        "source_run_key": source_run, "source_train_end": train_end,
        "train_split": train_split, "holdout_start": holdout_start,
        "last_source_day": days[-1], "symbols_scanned": scanned,
        "rules": len(veto), "statistics": dict(stats),
        "exits": dict(exits), "unknown_signals": dict(unknown),
        "selection": choose_train_only(stats),
    }


def store(conn, result, commit_sha):
    identity = "|".join((
        POLICIES_VERSION, result["source_run_key"], commit_sha,
        result["train_split"], result["holdout_start"], result["last_source_day"],
    ))
    key = hashlib.sha256(identity.encode()).hexdigest()[:32]
    ddl = Path("sql/013_dynamic_exit_research.sql").read_text(encoding="utf8")
    with conn.transaction():
        with conn.cursor() as cur:
            for sql in ddl.split(";"):
                if sql.strip():
                    cur.execute(sql)
            cur.execute("""INSERT INTO dynamic_exit_run
               (run_key,source_run_key,source_commit,train_split,train_end,
                holdout_start,last_source_day,policy_version,policy_count,
                rule_count,scanned_symbols,status,selected_policy)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (run_key) DO NOTHING""",
                (key, result["source_run_key"], commit_sha, result["train_split"],
                 result["source_train_end"], result["holdout_start"],
                 result["last_source_day"], POLICIES_VERSION, len(POLICIES),
                 result["rules"], result["symbols_scanned"], STATUS,
                 result["selection"]["selected"]))
            cur.executemany("""INSERT INTO dynamic_exit_stat
             (run_key,segment,cohort,policy,policy_parameters,events,observed,
              unknown,loss_count,positive_count,flat_count,loss5_count,
              net_sum_pct,paired_count,paired_wins,paired_harms,
              paired_candidate_loss5,paired_baseline_loss5,paired_delta_sum_pct)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
             ON CONFLICT DO NOTHING""",
                [(key, segment, cohort, policy, json.dumps(
                    POLICY_BY_NAME[policy].__dict__), b["events"], b["observed"],
                  b["unknown"], b["loss"], b["positive"], b["flat"],
                  b["loss5"], b["net_sum"], b["paired"], b["paired_wins"],
                  b["paired_harms"], b["paired_candidate_loss5"],
                  b["paired_baseline_loss5"], b["paired_delta_sum"])
                 for (segment, cohort, policy), b in result["statistics"].items()])
            cur.executemany("""INSERT INTO dynamic_exit_day
               (run_key,segment,cohort,policy,exit_day,exit_count,
                loss_count,net_sum_pct)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                [(key, seg, cohort, policy, day, v["count"], v["loss"],
                  v["net_sum"])
                 for ((seg, cohort, policy), day), v in result["exits"].items()])
    return key


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--write-db", action="store_true")
    p.add_argument("--train-split", default=TRAIN_SPLIT)
    p.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", "manual"))
    args = p.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Missing private DATABASE_URL")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], sslmode="require") as conn:
        result = from_neon(conn, args.train_split)
        key = store(conn, result, args.source_commit) if args.write_db else None
    p = result["selection"]["selected"]
    summary = {}
    for seg in ("TRAIN_A", "TRAIN_B", "HOLDOUT"):
        summary[seg] = {}
        for name in ("HOLD30", p) if p else ("HOLD30",):
            b = result["statistics"].get((seg, "SURVIVOR", name), blank())
            summary[seg][name] = {
                "events": b["events"], "observed": b["observed"],
                "unknown": b["unknown"], "negative_pct": round(
                    100 * b["loss"] / b["observed"], 3) if b["observed"] else None,
                "positive_pct": round(
                    100 * b["positive"] / b["observed"], 3) if b["observed"] else None,
                "mean_net_pct": round(b["net_sum"] / b["observed"], 4)
                if b["observed"] else None,
                "paired_count": b["paired"], "paired_prevented_losses": b["paired_wins"],
                "paired_introduced_losses": b["paired_harms"],
            }
    print(json.dumps({
        "status": STATUS, "version": POLICIES_VERSION,
        "policy_count": len(POLICIES), "source_run": result["source_run_key"],
        "rules": result["rules"], "symbols_scanned": result["symbols_scanned"],
        "source_through": result["last_source_day"],
        "selection": result["selection"], "summary": summary,
        "run_key": key, "stored": bool(key), "trading_approval": "NOT_APPROVED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
