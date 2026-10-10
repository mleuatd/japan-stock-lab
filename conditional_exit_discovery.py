#!/usr/bin/env python3
"""Explainable, evidence-led 30-session exit discovery (RESEARCH ONLY).

Instead of sweeping arbitrary stop-profit percent thresholds, this study:
1. describes point-in-time position *states* observed at each daily close;
2. measures counterfactual next-open exit vs same-position day-30 open HOLD;
3. discovers an interpretable one-condition rule on TRAIN_A;
4. adds a second condition only when it strengthens that earlier rationale;
5. checks the chosen rule in later TRAIN_B, then reports historical HOLDOUT.

No test-period outcomes influence which rules are tried or selected.
The 2026 period has been seen in previous studies; NOT fresh out-of-sample.
Every state is historical, only defined from information known by its close.
Corporate-action uncertainties, delistings and real trade fills still block
any brokerage recommendation.
"""
import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from downside_pattern_research import adjusted
from dynamic_exit_research import (
    MAX_HOLD, TRAIN_SPLIT, POLICY_BY_NAME, replay_exit, segment_ranges,
    valid_session, valid_open,
)
from risk_veto_union_audit import net_pct, read_train_rules, signal_status
from split_adjustment_guard import inspect_guard

VERSION = "conditional-eod-reasoning-v1"
STATUS = "RETROSPECTIVE_EXPLORATORY_NOT_APPROVED"
# The distinct features below are interpreted literally; no arbitrary
# data-fitted thresholds. Other combinations are *not* tried secretly.
FEATURES = {
    "AGE_01_05": ("age", "保有1～5日目"),
    "AGE_06_15": ("age", "保有6～15日目"),
    "AGE_16_28": ("age", "保有16～28日目"),
    "PNL_LOSS5": ("pnl", "現時点の含み損5%以上"),
    "PNL_LOSS2_5": ("pnl", "現時点の含み損2～5%"),
    "PNL_LOSS0_2": ("pnl", "現時点の含み損0～2%"),
    "PNL_GAIN0_2": ("pnl", "現時点の含み益0～2%"),
    "PNL_GAIN2_5": ("pnl", "現時点の含み益2～5%"),
    "PNL_GAIN5": ("pnl", "現時点の含み益5%以上"),
    "DRAWDOWN5": ("peak", "保有中の最高終値より5%以上安い"),
    "DRAWDOWN2_5": ("peak", "保有中の最高終値より2～5%安い"),
    "DRAWDOWN0_2": ("peak", "保有中の最高終値より0～2%安い"),
    "MOM3_DOWN3": ("momentum", "直近3日で3%以上下落"),
    "MOM3_DOWN0_3": ("momentum", "直近3日で0～3%下落"),
    "MOM3_UP0_3": ("momentum", "直近3日で0～3%上昇"),
    "MOM3_UP3": ("momentum", "直近3日で3%以上上昇"),
    "RED2": ("streak", "直近2日連続で前日比下落"),
    "RED3": ("streak", "直近3日連続で前日比下落"),
    "MA5_BELOW20": ("trend", "5日平均が20日平均より下"),
    "MA5_ATLEAST20": ("trend", "5日平均が20日平均以上"),
}
BIT = {name: 1 << n for n, name in enumerate(FEATURES)}
ATOMS = tuple(BIT)


def feature_mask(t, h, normalized, entry, peak):
    """Return only features known at END of held session h."""
    if not (1 <= h <= 28 and entry > 0):
        raise ValueError("Only 1..28 fully held EOD states are eligible")
    row = normalized.get(t + h)
    if not valid_session(row):
        return None
    close = row[0]
    names = []
    names.append("AGE_01_05" if h <= 5 else
                 "AGE_06_15" if h <= 15 else "AGE_16_28")
    ret = (close / entry - 1) * 100
    names.append("PNL_LOSS5" if ret <= -5 else
                 "PNL_LOSS2_5" if ret <= -2 else
                 "PNL_LOSS0_2" if ret < 0 else
                 "PNL_GAIN0_2" if ret < 2 else
                 "PNL_GAIN2_5" if ret < 5 else "PNL_GAIN5")
    dd = (close / max(peak, entry) - 1) * 100
    if dd <= -5:
        names.append("DRAWDOWN5")
    elif dd <= -2:
        names.append("DRAWDOWN2_5")
    else:
        names.append("DRAWDOWN0_2")
    past3 = normalized.get(t + h - 3)
    if past3 and past3[0] and past3[0] > 0:
        mom = (close / past3[0] - 1) * 100
        names.append("MOM3_DOWN3" if mom <= -3 else
                     "MOM3_DOWN0_3" if mom < 0 else
                     "MOM3_UP0_3" if mom < 3 else "MOM3_UP3")
    three = [normalized.get(t + h - j) for j in range(4)]
    if all(v is not None and v[0] is not None and v[0] > 0 for v in three):
        if three[0][0] < three[1][0] < three[2][0]:
            names.append("RED2")
            if three[2][0] < three[3][0]:
                names.append("RED3")
    candles = [normalized.get(t + h - j) for j in range(20)]
    if all(v is not None and v[0] is not None and v[0] > 0 for v in candles):
        ma5 = sum(v[0] for v in candles[:5]) / 5
        ma20 = sum(v[0] for v in candles) / 20
        names.append("MA5_BELOW20" if ma5 < ma20 else "MA5_ATLEAST20")
    return sum(BIT[n] for n in names)


def sample_episode(t, normalized):
    """Observed day30 baseline and full day1..28 next-open counterfactuals.

    Each exit is an *actual next day's observed OPEN* on adjusted-price scale.
    Missing 30-day path -> UNKNOWN episode, no made-up outcome.
    """
    base = replay_exit(t, normalized, POLICY_BY_NAME["HOLD30"])
    if base is None:
        return None
    first = normalized.get(t + 1)
    if not valid_session(first):
        return None
    entry = first[2]
    peak = entry
    options = []
    for h in range(1, MAX_HOLD - 1):
        row, nxt = normalized.get(t + h), normalized.get(t + h + 1)
        if not valid_session(row) or not valid_open(nxt):
            return None
        peak = max(peak, row[0])
        mask = feature_mask(t, h, normalized, entry, peak)
        if mask is None:
            return None
        options.append((mask, net_pct(entry, nxt[2]), h + 1))
    return (base["net"], options)


def policy_exit(sample, predicate):
    """The *first* matching EOD signal sells next OPEN; otherwise HOLD30."""
    baseline, options = sample
    for mask, net, day in options:
        if mask & predicate == predicate:
            return net, day
    return baseline, 30


def effect(samples, predicate):
    n = len(samples)
    out = {"n": n, "exit_count": 0, "prevented": 0,
           "introduced": 0, "baseline_loss": 0, "policy_loss": 0,
           "baseline_severe": 0, "policy_severe": 0, "baseline_net_sum": 0.,
           "policy_net_sum": 0., "exit_day_sum": 0}
    for sample in samples:
        old = sample[0]
        new, exit_day = policy_exit(sample, predicate)
        out["exit_count"] += exit_day < 30
        if exit_day < 30:
            out["exit_day_sum"] += exit_day
        out["baseline_loss"] += old < 0
        out["policy_loss"] += new < 0
        out["baseline_severe"] += old <= -5
        out["policy_severe"] += new <= -5
        out["prevented"] += old < 0 <= new
        out["introduced"] += new < 0 <= old
        out["baseline_net_sum"] += old
        out["policy_net_sum"] += new
    return out


def summarize_effect(row):
    n = row["n"]
    if not n:
        return {}
    return {
        "episodes": n,
        "exited_pct": round(100 * row["exit_count"] / n, 3),
        "loss_rate_baseline_pct": round(100 * row["baseline_loss"] / n, 3),
        "loss_rate_policy_pct": round(100 * row["policy_loss"] / n, 3),
        "paired_prevented": row["prevented"],
        "paired_introduced": row["introduced"],
        "loss_prevention_pp": round(
            100 * (row["prevented"] - row["introduced"]) / n, 3),
        "severe_prevention_pp": round(
            100 * (row["baseline_severe"] - row["policy_severe"]) / n, 3),
        "baseline_mean_net_pct": round(row["baseline_net_sum"] / n, 4),
        "policy_mean_net_pct": round(row["policy_net_sum"] / n, 4),
        "mean_net_delta_pp": round(
            (row["policy_net_sum"] - row["baseline_net_sum"]) / n, 4),
    }


def evidence_rank(row):
    """Within TRAIN_A only, prefer preventing *any* loss, then total profit.

    Report rather than conceal the tradeoff. Candidate and control use identical
    episodes and fee-adjusted execution; zero support cannot rank positively.
    """
    n = row["n"]
    if n < 150 or row["exit_count"] < 100:
        return None
    saved = row["prevented"] - row["introduced"]
    delta = (row["policy_net_sum"] - row["baseline_net_sum"]) / n
    # No severe-loss deterioration allowed even during discovery.
    if saved <= 0 or row["policy_severe"] > row["baseline_severe"]:
        return None
    return (saved / n, delta)


def discover(episodes):
    """One predicate, then optional conjunction; never search HOLDOUT.

    TRAIN_A picks top one-factor ideas then tests a restrained second
    independent factor (distinct feature families), with TRAIN_B used only
    to assess replication. No threshold optimization from later data.
    """
    a = episodes.get(("TRAIN_A", "SURVIVOR"), [])
    b = episodes.get(("TRAIN_B", "SURVIVOR"), [])
    if not a or not b:
        return {"selected": None, "state": "INSUFFICIENT_TRAIN_EPISODES",
                "investable": False}, []
    scored = []
    for name in ATOMS:
        r = effect(a, BIT[name])
        rank = evidence_rank(r)
        if rank is not None:
            scored.append((rank, name, BIT[name]))
    scored.sort(key=lambda x: (-x[0][0], -x[0][1], x[1]))
    seeds = scored[:4]
    discovered = {name: predicate for _, name, predicate in seeds}
    # Only a one-step explanation extension, conditional AND not arbitrary
    # combinations, and only different causal feature families.
    for _, parent_name, parent in seeds:
        family = FEATURES[parent_name][0]
        for child in ATOMS:
            if FEATURES[child][0] == family:
                continue
            names = sorted([parent_name, child])
            label = " & ".join(names)
            discovered[label] = parent | BIT[child]
    candidates = []
    for name, predicate in discovered.items():
        ra = effect(a, predicate)
        rank = evidence_rank(ra)
        if rank is None:
            continue
        candidates.append((rank, name, predicate, ra))
    candidates.sort(key=lambda x: (-x[0][0], -x[0][1], x[1]))
    # Decision is frozen by first-training-fold evidence; subsequent folds
    # confirm or reject, but never retune the rule to the tested future.
    best = candidates[0] if candidates else None
    if best is None:
        return {"selected": None, "state": "NO_TRAIN_A_PROMISING_STATE",
                "investable": False}, seeds
    rank, name, predicate, a_stat = best
    b_stat = effect(b, predicate)
    eb = summarize_effect(b_stat)
    repeated = (b_stat["n"] >= 150
                and b_stat["exit_count"] >= 100
                and b_stat["prevented"] > b_stat["introduced"]
                and b_stat["policy_severe"] <= b_stat["baseline_severe"])
    return {
        "selected": name, "predicate": predicate,
        "state": ("REPEATED_ANY_LOSS_REDUCTION_RETROSPECTIVE_ONLY"
                  if repeated else "NOT_REPLICATED_IN_TRAIN_B"),
        "train_a": summarize_effect(a_stat), "train_b": eb,
        "investable": False,
        "note": ("TRAIN_A discovers and selects; TRAIN_B only verifies. "
                 "Previously explored HOLDOUT is descriptive, not a pristine test."),
    }, seeds


def describe_conditional_day(episodes, segment, cohort):
    """Daily state-conditioned decision contrast; repeated days correlated."""
    buckets = defaultdict(lambda: {
        "n": 0, "hold_loss": 0, "exit_loss": 0,
        "prevented": 0, "introduced": 0, "hold_net": 0., "exit_net": 0.
    })
    for baseline, options in episodes.get((segment, cohort), []):
        for mask, exitnet, day in options:
            for feature, bit in BIT.items():
                if not mask & bit:
                    continue
                row = buckets[(day - 1, feature)]
                row["n"] += 1
                row["hold_loss"] += baseline < 0
                row["exit_loss"] += exitnet < 0
                row["prevented"] += baseline < 0 <= exitnet
                row["introduced"] += exitnet < 0 <= baseline
                row["hold_net"] += baseline
                row["exit_net"] += exitnet
    return buckets


def evaluate_one(code, obs, days, ranges, veto, episodes, unknown):
    norm = {i: adjusted(r) for i, r in obs.items()}
    for segment, first, last in ranges:
        last_spaced = -10000
        for t in range(first, last + 1):
            if t - last_spaced < 30:
                continue
            status, _ = signal_status(code, t, obs, norm, days, veto)
            if status not in ("EXCLUDED", "SURVIVOR"):
                unknown[(segment, status)] += 1
                continue
            last_spaced = t
            sample = sample_episode(t, norm)
            if sample is None:
                unknown[(segment, "UNKNOWN_FUTURE_PATH")] += 1
                continue
            episodes[(segment, "ALL")].append(sample)
            episodes[(segment, status)].append(sample)


def analyze(by_code, days, train_end, holdout_start, veto,
            train_split=TRAIN_SPLIT):
    ranges = segment_ranges(days, train_end, train_split, holdout_start)
    episodes = defaultdict(list)
    unknown = defaultdict(int)
    for code, obs in by_code.items():
        evaluate_one(code, obs, days, ranges, veto, episodes, unknown)
    return report(episodes, unknown)


def report(episodes, unknown):
    decision, seeds = discover(episodes)
    rule_names = sorted(set(ATOMS) | {k for _, k, _ in seeds}
                        | ({decision["selected"]} if decision["selected"] else set()))
    predicates = {name: BIT[name] for name in ATOMS}
    predicates.update({name: pred for _, name, pred in seeds})
    if decision["selected"]:
        predicates[decision["selected"]] = decision["predicate"]
    effects = {}
    daily = {}
    for seg in ("TRAIN_A", "TRAIN_B", "HOLDOUT"):
        for cohort in ("ALL", "SURVIVOR"):
            group = episodes.get((seg, cohort), [])
            for name in sorted(predicates):
                effects[(seg, cohort, name)] = effect(group, predicates[name])
            daily[(seg, cohort)] = describe_conditional_day(episodes, seg, cohort)
    if decision["selected"]:
        decision["holdout"] = summarize_effect(effects.get(
            ("HOLDOUT", "SURVIVOR", decision["selected"]), {}))
    return {"decision": decision, "rule_labels": {n: (
        " AND ".join(FEATURES[p][1] for p in n.split(" & "))
        if " & " in n else FEATURES[n][1]) for n in predicates},
        "effects": effects, "daily": daily, "unknown": dict(unknown),
        "episode_counts": {f"{s}:{c}": len(episodes.get((s,c), []))
                           for s in ("TRAIN_A","TRAIN_B","HOLDOUT")
                           for c in ("ALL","SURVIVOR")}}


def from_neon(conn, train_split=TRAIN_SPLIT):
    blocked, split_audit = inspect_guard(conn)
    source, holdout_start, rules = read_train_rules(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT train_end FROM downside_pattern_run_v2 WHERE run_key=%s",
                    (source,))
        train_end = cur.fetchone()[0].isoformat()
        cur.execute("SELECT DISTINCT trading_date FROM daily_bar ORDER BY trading_date")
        days = [d[0].isoformat() for d in cur]
    ranges = segment_ranges(days, train_end, train_split, holdout_start)
    idx = {d: i for i, d in enumerate(days)}
    episodes = defaultdict(list)
    unknown = defaultdict(int)
    current, obs, scanned = None, {}, 0
    veto = {v["code"] for v in rules}
    with conn.cursor(name="private_state_reason_stream") as cur:
        cur.itersize = 15000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,
                 open_price,high_price,low_price,close_price,volume
                 FROM daily_bar ORDER BY security_code,trading_date""")
        for code, day, adj, op, hi, lo, close, vol in cur:
            if code in blocked:
                continue
            if current is not None and current != code:
                evaluate_one(current, obs, days, ranges, veto, episodes, unknown)
                scanned += 1
                obs = {}
            current = code
            obs[idx[day.isoformat()]] = {
                "adjusted_close": float(adj) if adj is not None else None,
                "open_price": float(op) if op is not None else None,
                "high_price": float(hi) if hi is not None else None,
                "low_price": float(lo) if lo is not None else None,
                "close_price": float(close) if close is not None else None,
                "volume": float(vol) if vol is not None else None}
        if current is not None:
            evaluate_one(current, obs, days, ranges, veto, episodes, unknown)
            scanned += 1
    r = report(episodes, unknown)
    r.update(source_run=source, train_split=train_split, train_end=train_end,
             holdout_start=holdout_start, source_through=days[-1],
             scan_count=scanned, split_audit=split_audit)
    return r


def store(conn, r, commit):
    token = "|".join([VERSION, r["source_run"], r["train_split"],
                      r["holdout_start"], r["source_through"],
                      r["split_audit"]["guard_version"], commit])
    key = hashlib.sha256(token.encode()).hexdigest()[:32]
    ddl = Path("sql/016_conditional_exit_discovery.sql").read_text(encoding="utf8")
    with conn.transaction():
        with conn.cursor() as cur:
            for statement in ddl.split(";"):
                if statement.strip():
                    cur.execute(statement)
            cur.execute("""INSERT INTO conditional_exit_run
                (run_key, source_run, commit_sha, version, train_split, train_end,
                 holdout_start, source_through, scanned_symbols, decision, status)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                 ON CONFLICT DO NOTHING""",
                (key, r["source_run"], commit, VERSION, r["train_split"],
                 r["train_end"], r["holdout_start"], r["source_through"],
                 r["scan_count"], json.dumps(r["decision"]), STATUS))
            rows = []
            for (seg, cohort, name), b in r["effects"].items():
                rows.append((key,seg,cohort,name,r["rule_labels"][name],
                             b["n"],b["exit_count"],b["prevented"],b["introduced"],
                             b["baseline_loss"],b["policy_loss"],b["baseline_severe"],
                             b["policy_severe"],b["baseline_net_sum"],b["policy_net_sum"]))
            cur.executemany("""INSERT INTO conditional_exit_effect
                (run_key, segment, cohort, rule, explanation,
                 episodes, exit_count, prevented, introduced,
                 baseline_loss, policy_loss, baseline_severe, policy_severe,
                 baseline_net_sum, policy_net_sum)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                 ON CONFLICT DO NOTHING""", rows)
            dayrows = []
            for (seg, cohort), buckets in r["daily"].items():
                for (heldday, feature), b in buckets.items():
                    dayrows.append((key,seg,cohort,heldday,feature,b["n"],
                         b["hold_loss"],b["exit_loss"],b["prevented"],b["introduced"],
                         b["hold_net"],b["exit_net"]))
            cur.executemany("""INSERT INTO conditional_exit_day
                 (run_key,segment,cohort,held_day,feature,observations,
                  hold_loss,next_open_loss,prevented,introduced,
                  hold_net_sum,next_open_net_sum)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                 ON CONFLICT DO NOTHING""",dayrows)
    return key


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--write-db",action="store_true")
    p.add_argument("--train-split",default=TRAIN_SPLIT)
    p.add_argument("--source-commit",default=os.environ.get("GITHUB_SHA","manual"))
    a = p.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Missing DATABASE_URL")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"],sslmode="require") as conn:
        r = from_neon(conn,a.train_split)
        key = store(conn,r,a.source_commit) if a.write_db else None
    print(json.dumps({
        "status": STATUS, "run_key": key, "stored": bool(key),
        "source_through": r["source_through"], "symbols_scanned":r["scan_count"],
        "episode_counts":r["episode_counts"], "decision":r["decision"],
        "conditional_state_records":sum(len(v) for v in r["daily"].values()),
        "feature_families":sorted({x[0] for x in FEATURES.values()}),
        "trading_approval":"NOT_APPROVED"
    }, ensure_ascii=False))


if __name__=="__main__":
    main()
