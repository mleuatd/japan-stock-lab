"""Regression: an unsellable opening must not silently cancel a held-stock exit."""
import unittest
from walkforward_backtest import Bar, simulate


class SuspendedSellRetryTest(unittest.TestCase):
    def test_retry_sell_after_missing_open(self):
        dates=["2026-02-02","2026-02-03","2026-02-04","2026-02-05","2026-02-06"]
        data={}
        for i,day in enumerate(dates):
            # No bar on day 4: selling is impossible, but the holding remains.
            if i == 3:
                data[day]={}
            else:
                data[day]={"1111":Bar(day,"1111",100.,100.,1000,100.)}
        result=simulate(data,{"lookback":1,"min_return_pct":0,"min_volume":1},
                        initial_cash=500000,allocation=0.5,hold_days=1)
        sells=[e for e in result["events"] if e.get("side")=="SELL"]
        self.assertTrue(any(e["action"]=="SKIP_NO_OPEN" and e["date"]==dates[3] for e in sells))
        self.assertTrue(any(e["action"]=="FILLED" and e["date"]==dates[4] for e in sells))
        self.assertEqual(result["open_positions"],{})
        self.assertGreaterEqual(result["ending_cash"],0)
        self.assertFalse(any(o["side"]=="SELL" for o in result["unfilled_last_day_orders"]))


if __name__=="__main__":
    unittest.main()
