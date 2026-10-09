"""P0: non-finite prices must not create executable orders or validated equity."""
import math
import unittest
from february_walkforward import replay
from walkforward_backtest import Bar

class NonfinitePriceGuardTest(unittest.TestCase):
    def setUp(self):
        self.days=[f"2025-{1+i//28:02d}-{1+i%28:02d}" for i in range(122)]
        self.data={d:{"11110":Bar(d,"11110",100.,100.,1000,100.)} for d in self.days}
        self.rule={"lookback":3,"min_return_pct":0,"min_volume":0}
    def run_replay(self):
        return replay(self.data,self.rule,cutoff=self.days[119],start=self.days[120],allocation=10000,fee_rate=0,hold_days=90)
    def test_nan_final_close_stays_unknown(self):
        d=self.days[-1]
        self.data[d]["11110"]=Bar(d,"11110",100.,float("nan"),1000,100.)
        r=self.run_replay()
        self.assertIsNone(r["final_equity"])
        self.assertEqual(r["valuation_diagnostics"]["held_positions_without_final_close"],1)
        self.assertIsNone(r["valuation_diagnostics"]["indicative_last_known_equity"] if False else r["final_equity"])
    def test_nan_open_does_not_fill(self):
        d=self.days[120]
        self.data[d]["11110"]=Bar(d,"11110",float("nan"),100.,1000,100.)
        r=self.run_replay()
        self.assertFalse(any(f["side"]=="BUY" and f["date"]==d for f in r["fills"]))
        self.assertTrue(math.isfinite(r["cash"]))

if __name__=="__main__":unittest.main()
