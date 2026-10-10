"""J-Quants corporate action quality regression: never invent split crashes."""
import unittest

from downside_pattern_research import adjusted, detect
from risk_veto_union_audit import net_pct
from split_adjustment_guard import inspect_guard, split_transition_ok, TOLERANCE


class FakeCursor:
    def __init__(self, summary, codes):
        self.summary, self.codes, self.query_count = summary, codes, 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql):
        self.query_count += 1
        return self

    def fetchone(self):
        return self.summary

    def fetchall(self):
        return [(x,) for x in self.codes]


class FakeConn:
    def __init__(self, summary, codes):
        self.fake_cursor = FakeCursor(summary, codes)

    def cursor(self):
        return self.fake_cursor


def price(raw_close, adjusted_close):
    return {"close_price": raw_close, "adjusted_close": adjusted_close,
            "open_price": raw_close, "high_price": raw_close * 1.01,
            "low_price": raw_close * .99, "volume": 10000}


class SplitIntegrityTests(unittest.TestCase):
    def test_split_and_reverse_split_factors(self):
        self.assertTrue(split_transition_ok(0.5, 1.0, 0.5))
        self.assertTrue(split_transition_ok(10.0, 1.0, 10.0))
        self.assertTrue(split_transition_ok(1/3, 1.0, 1/3))
        self.assertFalse(split_transition_ok(0.4, 1.0, 0.5))
        self.assertFalse(split_transition_ok(1.0, 1.0, 0.5))
        self.assertEqual(TOLERANCE, 0.005)

    def test_missing_adj_close_is_not_accepted(self):
        self.assertIsNone(split_transition_ok(None, 1, .5))
        self.assertIsNone(split_transition_ok(0, 1, .5))
        self.assertIsNone(split_transition_ok(.5, float("nan"), .5))

    def test_split_adjusted_profit_and_veto_patterns(self):
        # A 2-for-1 split is not a -48% overnight market loss.
        before = price(100.0, 50.0)
        after = price(52.0, 52.0)
        b0, b1 = adjusted(before), adjusted(after)
        self.assertAlmostEqual(b0[0], 50.0)
        self.assertAlmostEqual(b0[2], 50.0)
        self.assertAlmostEqual(b1[2], 52.0)
        self.assertAlmostEqual(net_pct(b0[2], b1[2]), 3.79220779220779)
        self.assertLess(net_pct(100, 52), -47)  # WRONG if raw shares ignored.
        history = [price(100, 50) for _ in range(20)] + [after]
        found = detect(history)
        self.assertNotIn("R01_DOWN10", found)
        self.assertNotIn("R01_DOWN05", found)
        self.assertIn("R01_UP01", found)

    def test_incomplete_boundary_is_excluded_and_good_splits_kept(self):
        with self.assertRaises(ValueError):
            inspect_guard(FakeConn((453, 441, 12, 428, 12),
                                   {"UNKNOWN1", "UNKNOWN2"}))

    def test_full_consistent_blocklist(self):
        blocked, counts = inspect_guard(
            FakeConn((453, 441, 12, 428, 2), {"BROKEN1", "BROKEN2"}))
        self.assertEqual(blocked, {"BROKEN1", "BROKEN2"})
        self.assertEqual(counts["verified_events"], 441)
        self.assertEqual(counts["excluded_tickers"], 2)
        self.assertEqual(counts["guard_version"], "jquants-split-guard-v1")

    def test_mismatched_event_coverage_fails_closed(self):
        for summary, blocked in (
            ((0, 0, 0, 0, 0), set()),
            ((453, 440, 12, 428, 12), set(range(12))),
            ((453, 441, 12, 428, 12), {"ONE"}),
            ((10, 0, 10, 0, 11), set(range(11))),
        ):
            with self.subTest(summary=summary):
                with self.assertRaises(ValueError):
                    inspect_guard(FakeConn(summary, blocked))


if __name__ == "__main__":
    unittest.main()
