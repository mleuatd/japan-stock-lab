"""Regression tests: a missing/invalid held close cannot silently become zero equity."""
import unittest
from walkforward_backtest import Bar, simulate
from fast_strategy_grid import replay

class UnknownEquityTests(unittest.TestCase):
    def test_walkforward_zero_held_close_is_unknown(self):
        dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
        bars = {
            dates[0]: {"11110": Bar(dates[0], "11110", 100, 100, 1000, 100)},
            dates[1]: {"11110": Bar(dates[1], "11110", 110, 110, 1000, 110)},
            dates[2]: {"11110": Bar(dates[2], "11110", 120, 0, 1000, 120)},
        }
        result = simulate(bars, {"lookback": 1, "min_return_pct": 5},
                          initial_cash=10000, allocation=1, lot_size=1, hold_days=5)
        self.assertEqual(len(result["fills"]), 1)
        self.assertIsNone(result["equity_curve"][-1]["equity"])

    def test_grid_zero_held_close_is_unknown(self):
        dates = ["2025-01-01", "2025-01-02"]
        bars = {
            dates[0]: {"11110": Bar(dates[0], "11110", 100, 100, 1000, 100)},
            dates[1]: {"11110": Bar(dates[1], "11110", 110, 0, 1000, 110)},
        }
        features = {dates[0]: {"11110": (1, 4, 10, 2, True)},
                    dates[1]: {"11110": (1, 4, 10, 2, True)}}
        result = replay(bars, dates, features, "momentum", "five_day",
                        dates[1], dates[1], initial=10000, per_position=10000, lot=1)
        self.assertEqual(result["fills"], 1)
        self.assertIsNone(result["ending_equity"])
        self.assertIsNone(result["net_pnl"])

if __name__ == "__main__":
    unittest.main()
