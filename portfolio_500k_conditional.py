#!/usr/bin/env python3
"""Private, historical JPY 500,000 cash portfolio sanity check.

Frozen earlier BUY condition (3-day return >= -10%, zero volume threshold).
Compare (i) old five-day exit, (ii) hold-to-day-30 OPEN, and
(iii) EOD +2..+5% P&L band -> next day OPEN else day30 OPEN.
No new entry rule is fitted on 2026 data. Real purchase/market performance
remains NOT APPROVED (dividends, taxes, complete as-of listings unverified).
"""
import json
import os
from collections import defaultdict

from february_walkforward import CUTOFF, START, load_private_neon, replay
from split_adjustment_guard import inspect_guard

INITIAL = 500000
FROZEN_BUY = {"lookback": 3, "min_return_pct": -10, "min_volume": 0}
STATUS = "HISTORICAL_PAPER_UNVERIFIED_NOT_FOR_TRADING"


def fetch_audited_actions(conn):
    """Use official J-Quants AdjFactor only on a verified ex-date."""
    blocked, quality = inspect_guard(conn)
    actions = defaultdict(dict)
    with conn.cursor() as cur:
        cur.execute("""SELECT security_code, trading_date, adjustment_factor
            FROM split_adjustment_integrity_events
            WHERE audit_status='VERIFIED_SPLIT_ADJUSTMENT'
              AND trading_date >= %s::date
            ORDER BY trading_date, security_code""", (START,))
        for code, day, factor in cur:
            if code in blocked:
                continue
            if factor is None or factor <= 0:
                raise ValueError("Unverifiable corporate adjustment factor")
            actions[day.isoformat()][code] = {"split_ratio": 1.0 / float(factor)}
    return blocked, dict(actions), quality


def summary(result):
    fills = [r for r in result["fills"] if r.get("side") in ("BUY", "SELL")]
    diag = result["valuation_diagnostics"]
    eq = result["final_equity"]
    cash = result["cash"]
    return {
        "ending_cash_jpy": cash,
        "final_equity_jpy": eq,
        "final_pnl_jpy": (round(eq-INITIAL, 2) if eq is not None else None),
        "final_return_pct": (round(100*(eq/INITIAL-1), 4)
                             if eq is not None else None),
        "indicative_stale_mark_jpy": diag["indicative_last_known_equity"],
        "unpriced_days": diag["unpriced_days"],
        "held_stocks": len(result["held"]),
        "buy_fills": sum(x["side"] == "BUY" for x in fills),
        "sell_fills": sum(x["side"] == "SELL" for x in fills),
        "realized_profit_jpy": result["realized_pnl"],
        "unrealized_profit_jpy": result["unrealized_pnl"],
        "known_dividends_jpy": result["known_net_dividends"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "unfilled_after_final_day": len(result["unfilled_after_final_session"]),
        "split_actions_applied": sum(x.get("status")=="SPLIT"
                                     for x in result["fills"]),
        "known_listing_risk_skips": result["listing_risk_screen"]["buy_signals_or_fills_skipped"],
    }


def calculate(data, verified_actions):
    if not data or max(data) != "2026-07-17":
        raise ValueError("Historical source changed: date scope must be reaudited")
    shared = dict(cutoff=CUTOFF, start=START, initial=INITIAL,
                  lot=100, allocation=100000, max_positions=5,
                  fee_rate=0.001, tax_rate=0.0, slippage_rate=0.0,
                  corporate_actions=verified_actions)
    candidates = {
        "PRIOR_HOLD5": dict(hold_days=5),
        "HOLD30": dict(hold_days=30, max_hold_at_open=True),
        "GAIN2_TO5_THEN_HOLD30": dict(
            hold_days=30, max_hold_at_open=True, take_profit_band=(2,5)),
    }
    return {name: summary(replay(data, FROZEN_BUY, **shared, **params))
            for name, params in candidates.items()}


def main():
    import psycopg
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Missing DATABASE_URL")
    with psycopg.connect(os.environ["DATABASE_URL"], sslmode="require") as conn:
        blocked, actions, quality = fetch_audited_actions(conn)
    # Only Jan 2026 onward is required for the fixed 3-day entry lookback.
    # A bounded SQL query avoids the unnecessary ~1.3m earlier price rows.
    raw = load_private_neon(since="2026-01-01") # private prices, NEVER published
    data = {d: {code: bar for code, bar in bars.items()
                if code not in blocked} for d, bars in raw.items()}
    results = calculate(data, actions)
    print("PORTFOLIO_500K "+json.dumps({
        "status": STATUS,
        "historical_window": [START, max(data)],
        "initial_jpy": INITIAL,
        "entry_rule": "prior preselected 3d return >= -10% (NOT newly validated)",
        "trading": "cash only; buy in 100-share lots; next-open; night-only",
        "costs": "0.1% one-way; 0 tax; 0 slippage; no dividends",
        "corporate_quality": quality,
        "strategy_comparison": results,
        "approval": "NOT_APPROVED",
        "critical_limits": [
            "Earlier selected buy condition already explored in the evaluated period",
            "Corporate actions other than split/consolidation, full listing history unverified",
            "Split cash-in-lieu and cash dividend payments not completely available",
            "Actual lot fills/realistic liquidity/slippage/tax are not proven",
            "Stale source through 2026-07-17; no current trades",
            "A missing portfolio valuation day disqualifies claims of reliable drawdown",
        ],
    },ensure_ascii=False))


if __name__=="__main__":
    main()
