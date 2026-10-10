import unittest
from datetime import date, timedelta

from downside_pattern_research import CATALOG
from risk_veto_union_audit import (
    add_bucket, evaluate_rows, fresh_bucket, future_outcomes, net_pct,
    signal_status, train_only_rules,
)


def candle(p, low=None, open_price=None, volume=1000):
    op = p if open_price is None else open_price
    lo = min(op, p) - 2 if low is None else low
    return {"adjusted_close": p, "close_price": p,
            "open_price": op, "high_price": max(op, p) + 2,
            "low_price": lo, "volume": volume}


def stat(code, segment, rate):
    return {"pattern_code": code, "segment": segment, "horizon": 20,
            "observed_count": 5000, "path_complete_count": 5000,
            "total_count": 5000, "missing_count": 0,
            "unique_symbols": 250, "down_pct": rate,
            "close_loss5_pct": rate, "touch_loss5_pct": rate}


class UnionResearchTests(unittest.TestCase):
    def test_catalog_exhaustive_and_test_not_used_for_rule_training(self):
        self.assertEqual(len(CATALOG), 121)
        rows = [
            stat("BASE", "train", 30),
            stat("R01_DOWN01", "train", 70),
            stat("R01_DOWN01", "holdout", 0),
            stat("BASE", "holdout", 100),
        ]
        chosen = train_only_rules(rows)
        self.assertEqual([v["code"] for v in chosen], ["R01_DOWN01"])
        self.assertEqual(chosen[0]["metric"], "touch_loss5_pct")
        rows[2]["touch_loss5_pct"] = 100
        rows[3]["touch_loss5_pct"] = 0
        self.assertEqual(train_only_rules(rows), chosen)

    def test_next_open_entry_cost_and_intraday_loss(self):
        normalized = {1: (100, 1000, 100, 101, 98),
                      2: (101, 1000, 101, 102, 90),
                      3: (105, 1000, 103, 106, 99)}
        out = dict(future_outcomes(0, normalized, range(1, 4)))
        self.assertLess(out[1]["net"], 0)
        self.assertTrue(out[2]["close3"] is False)
        self.assertLess(out[2]["path"], -5)
        self.assertLess(out[3]["path"], -5)
        self.assertLess(net_pct(100, 100), 0)

    def test_zero_volume_open_is_not_an_executable_trade(self):
        normalized = {1: (100, 0, 100, 101, 98),
                      2: (95, 1000, 95, 100, 90)}
        outcomes = dict(future_outcomes(0, normalized, range(1, 3)))
        self.assertIsNone(outcomes[1])
        self.assertIsNone(outcomes[2])

    def test_missing_path_is_unknown_not_safe(self):
        normalized = {1: (100, 1000, 100, 101, 98),
                      2: (102, 1000, 100, 103, None),
                      3: (103, 1000, 100, 103, 100)}
        out = dict(future_outcomes(0, normalized, range(1, 4)))
        self.assertIsNotNone(out[2])
        self.assertIsNone(out[2]["path"])
        self.assertIsNone(out[3]["path"])
        b = fresh_bucket()
        add_bucket(b, out[2])
        self.assertEqual(b["path_unknown"], 1)
        self.assertEqual(b["path_complete"], 0)

    def test_missing_future_close_increases_missing_not_observed(self):
        normalized = {1: (100, 1000, 100, 101, 98),
                      2: None}
        future = dict(future_outcomes(0, normalized, range(1, 3)))
        b = fresh_bucket()
        add_bucket(b, future[1])
        add_bucket(b, future[2])
        self.assertEqual((b["events"], b["observed"], b["missing"]), (2, 1, 1))

    def test_incomplete_21_day_chart_not_a_zero_match(self):
        days = [(date(2026, 2, 2) + timedelta(days=i)).isoformat()
                for i in range(25)]
        obs = {i: candle(100 + i) for i in range(21)}
        obs[5] = candle(105, volume=0)
        from downside_pattern_research import adjusted
        norm = {i: adjusted(bar) for i, bar in obs.items()}
        state, _ = signal_status("9999", 20, obs, norm, days, set())
        self.assertEqual(state, "UNKNOWN_INVALID_OHLCV")
        obs[5] = candle(105)
        del obs[5]
        norm = {i: adjusted(bar) for i, bar in obs.items()}
        state, _ = signal_status("9999", 20, obs, norm, days, set())
        self.assertEqual(state, "UNKNOWN_MISSING_CHART_DAYS")

    def test_full_maturity_and_cohort_accounting(self):
        days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat()
                for i in range(90)]
        bars = {"9999": {i: candle(110 - i * .2)
                          for i in range(90)}}
        tested = evaluate_rows(bars, days, {"BASE"}, "2026-02-02")
        self.assertEqual(tested["signal_end"], days[-31])
        twenty = tested["cohorts"][("daily", "EXCLUDED", 20)]
        all_rows = tested["cohorts"][("daily", "ALL", 20)]
        self.assertEqual(twenty, all_rows)
        self.assertGreater(twenty["observed"], 0)
        self.assertEqual(twenty["losses"], twenty["observed"])
        self.assertEqual(len(tested["snapshot"]), 1)
        self.assertEqual(tested["snapshot"][0][2], "EXCLUDED")

    def test_unknown_is_not_in_baseline_or_survivors(self):
        days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat()
                for i in range(90)]
        bars = {"9999": {i: candle(100) for i in range(90)},
                "9998": {i: candle(100) for i in range(90)}}
        bars["9998"][40]["low_price"] = 999
        result = evaluate_rows(bars, days, set(), "2026-02-02")
        self.assertGreater(result["unknown_signals"].get("UNKNOWN_INVALID_OHLCV", 0), 0)
        for cohort in ("ALL", "SURVIVOR"):
            bucket = result["cohorts"][("daily", cohort, 20)]
            self.assertEqual(bucket["events"], bucket["observed"] + bucket["missing"])
            self.assertGreater(bucket["missing"], 0)


if __name__ == "__main__":
    unittest.main()
