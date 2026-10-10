"""Adaptive EOD research: gaps, train-only selection, 30-session maturity."""
import copy
import unittest
from collections import defaultdict
from datetime import date, timedelta

from dynamic_exit_research import (
    MAX_HOLD, POLICIES, POLICY_BY_NAME, Policy, analyze, blank, choose_train_only,
    count, replay_exit, segment_ranges,
)


def bar(close=100, opening=None, volume=1000):
    opening = close if opening is None else opening
    return (close, volume, opening, max(close, opening) + 2,
            min(close, opening) - 2)


def sample(last=100):
    # t=0 is end-of-day signal; h=1 is purchase at following OPEN.
    norm = {0: bar(100)}
    for h in range(1, 31):
        norm[h] = bar(last if h == 30 else 100)
    return norm


class DynamicExitTests(unittest.TestCase):
    def test_predeclared_grid_and_validation(self):
        self.assertEqual(MAX_HOLD, 30)
        self.assertEqual(len(POLICIES), 23)
        self.assertEqual(len(POLICY_BY_NAME), len(POLICIES))
        for invalid in (dict(fixed_day=0), dict(fixed_day=31),
                        dict(stop_close=-2), dict(pattern="UNKNOWN")):
            with self.assertRaises(ValueError):
                Policy("BAD", **invalid)

    def test_baseline_matures_at_30th_open_without_future_close(self):
        norm = sample()
        norm[30] = bar(close=500, opening=102)
        x = replay_exit(0, norm, POLICY_BY_NAME["HOLD30"])
        self.assertEqual((x["day"], x["reason"], x["exit"]),
                         (30, "MAX_HOLD_OPEN", 102))
        self.assertLess(x["net"], 2)  # Round-trip fees.
        norm[30] = bar(close=1, opening=102)
        self.assertEqual(replay_exit(0, norm, POLICY_BY_NAME["HOLD30"]), x)

    def test_day1_close_stop_only_exits_day2_open_with_gap(self):
        norm = sample()
        norm[1] = bar(close=97, opening=100)
        norm[2] = bar(close=99, opening=91)
        out = replay_exit(0, norm, POLICY_BY_NAME["STOP_CLOSE2"])
        self.assertEqual((out["day"], out["reason"], out["exit"]),
                         (2, "STOP_CLOSE", 91))
        self.assertLess(out["net"], -9)

    def test_no_peek_into_future_after_early_exit(self):
        norm = sample()
        norm[1] = bar(close=98, opening=100)
        norm[2] = bar(close=100, opening=96)
        policy = POLICY_BY_NAME["STOP_CLOSE2"]
        prior = replay_exit(0, norm, policy)
        for h in range(3, 31):
            norm[h] = bar(close=0.01)
        self.assertEqual(replay_exit(0, norm, policy), prior)

    def test_fixed_day_exit_at_next_open(self):
        norm = sample()
        norm[5] = bar(close=100, opening=100)
        norm[6] = bar(close=104, opening=103)
        result = replay_exit(0, norm, POLICY_BY_NAME["DAY05"])
        self.assertEqual((result["day"], result["reason"], result["exit"]),
                         (6, "FIXED_DAY_CLOSE", 103))

    def test_target_and_trailing_exit(self):
        norm = sample()
        norm[1] = bar(close=106, opening=100)
        norm[2] = bar(close=97, opening=101)
        target = replay_exit(0, norm, POLICY_BY_NAME["TARGET_CLOSE5"])
        self.assertEqual((target["day"], target["exit"]), (2, 101))
        trail = replay_exit(0, norm, POLICY_BY_NAME["TRAIL_CLOSE3"])
        self.assertEqual((trail["day"], trail["reason"]), (3, "TRAIL_CLOSE"))

    def test_two_red_pattern_uses_only_post_entry_closes(self):
        norm = sample()
        norm[0] = bar(104)
        norm[1] = bar(close=99, opening=100)
        norm[2] = bar(close=98, opening=98.5)
        norm[3] = bar(close=97, opening=97.5)
        result = replay_exit(0, norm, POLICY_BY_NAME["PATTERN_TWO_RED"])
        self.assertEqual((result["day"], result["reason"]), (3, "PATTERN_TWO_RED"))

    def test_missing_candle_and_no_volume_remain_unknown(self):
        norm = sample()
        norm[2] = None
        self.assertIsNone(replay_exit(0, norm, POLICY_BY_NAME["STOP_CLOSE2"]))
        norm = sample()
        norm[2] = bar(close=100, opening=95, volume=0)
        self.assertIsNone(replay_exit(0, norm, POLICY_BY_NAME["STOP_CLOSE2"]))
        norm = sample()
        norm[30] = bar(close=100, opening=100, volume=0)
        self.assertIsNone(replay_exit(0, norm, POLICY_BY_NAME["HOLD30"]))

    def test_invalid_adjusted_bar_is_unknown(self):
        norm = sample()
        norm[4] = (100, 1000, 100, 95, 80)
        self.assertIsNone(replay_exit(0, norm, POLICY_BY_NAME["HOLD30"]))

    def test_no_nontrade_or_unknown_is_counted_as_win(self):
        s = blank()
        baseline = {"net": -2}
        count(s, None, baseline)
        count(s, {"net": 1}, baseline)
        count(s, {"net": -6}, baseline)
        self.assertEqual((s["events"], s["unknown"], s["observed"]), (3, 1, 2))
        self.assertEqual((s["paired"], s["paired_wins"], s["paired_harms"]),
                         (2, 1, 0))
        self.assertEqual((s["positive"], s["loss"], s["loss5"]), (1, 1, 1))

    def test_training_selection_never_looks_at_holdout(self):
        rows = defaultdict(blank)
        for fold in ("TRAIN_A", "TRAIN_B"):
            b = rows[(fold, "SURVIVOR", "STOP_CLOSE2")]
            b.update(events=500, observed=500, paired=500, paired_wins=90,
                     paired_harms=20, paired_candidate_loss5=5,
                     paired_baseline_loss5=30, paired_delta_sum=110.0)
        chosen = choose_train_only(rows)
        self.assertEqual(chosen["selected"], "STOP_CLOSE2")
        rows[("HOLDOUT", "SURVIVOR", "STOP_CLOSE2")].update(
            events=9000, observed=9000, paired=9000, paired_wins=0,
            paired_harms=9000, paired_delta_sum=-100000.0)
        self.assertEqual(choose_train_only(rows), chosen)

    def test_loss_only_without_mean_return_improvement_is_rejected(self):
        rows = defaultdict(blank)
        for fold in ("TRAIN_A", "TRAIN_B"):
            rows[(fold, "SURVIVOR", "STOP_CLOSE2")].update(
                events=500, observed=500, paired=500, paired_wins=100,
                paired_harms=10, paired_delta_sum=-1.0)
        self.assertIsNone(choose_train_only(rows)["selected"])

    def test_overfitting_one_fold_is_rejected(self):
        rows = defaultdict(blank)
        for fold, wins, harms in (("TRAIN_A", 90, 5), ("TRAIN_B", 10, 40)):
            rows[(fold, "SURVIVOR", "STOP_CLOSE2")].update(
                events=500, observed=500, paired=500, paired_wins=wins,
                paired_harms=harms, paired_delta_sum=200.0)
        self.assertIsNone(choose_train_only(rows)["selected"])

    def test_maturity_windows_do_not_cross_train_or_holdout(self):
        days = [(date(2024, 10, 8) + timedelta(days=i)).isoformat()
                for i in range(720)]
        ranges = segment_ranges(days, "2026-01-30", "2025-07-01", "2026-02-02")
        self.assertEqual([seg for seg, _, _ in ranges],
                         ["TRAIN_A", "TRAIN_B", "HOLDOUT"])
        index = {day: i for i, day in enumerate(days)}
        self.assertLess(ranges[0][2] + 30, index["2025-07-01"])
        self.assertLessEqual(ranges[1][2] + 30, index["2026-01-30"])
        self.assertLessEqual(ranges[2][2] + 30, len(days) - 1)


if __name__ == "__main__":
    unittest.main()
