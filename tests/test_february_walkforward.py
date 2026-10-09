import datetime as dt
import unittest
from february_walkforward import experiment,replay,frozen_train
from walkforward_backtest import Bar

def bar(d,p,code="11110"):
    return Bar(d,code,p,p,1000000,p)
class FebruaryWalkforwardTest(unittest.TestCase):
    def setUp(self):
        self.data={}
        start=dt.date(2025,8,1)
        for i in range(180):
            d=(start+dt.timedelta(days=i)).isoformat()
            self.data[d]={"11110":bar(d,100+i*.4),
                          "22220":bar(d,200+i*.1,code="22220")}
        self.cutoff=sorted(self.data)[145];self.start=sorted(self.data)[146]
    def test_trained_rule_is_independent_of_any_post_cutoff_data(self):
        before=frozen_train(self.data,self.cutoff,min_events=2)
        modified={d:dict(x) for d,x in self.data.items()}
        for day in modified:
            if day>self.cutoff:
                modified[day]["11110"]=bar(day,999999)
        after=frozen_train(modified,self.cutoff,min_events=2)
        self.assertEqual(before,after)
    def test_replay_never_trades_before_start(self):
        result=replay(self.data,{"lookback":3,"min_return_pct":0,"min_volume":0},
                      cutoff=self.cutoff,start=self.start,lot=100,allocation=30000)
        self.assertTrue(all(f["date"]>=self.start for f in result["fills"]))
        self.assertTrue(all(d["date"]>=self.start for d in result["equity"]))
        self.assertTrue(all(x["side"] in ("BUY","SELL") for x in result["fills"]))
        self.assertGreaterEqual(result["cash"],0)
    def test_ending_equity_is_not_identical_to_cash_if_holdings_exist(self):
        result=replay(self.data,{"lookback":3,"min_return_pct":0},
                      cutoff=self.cutoff,start=self.start,lot=100,allocation=30000,hold_days=999)
        self.assertGreaterEqual(result["equity"][-1]["total_equity"],result["cash"])
    def test_no_pre_cutoff_data(self):
        with self.assertRaises(ValueError):
            frozen_train({"2026-01-30":{"11110":bar("2026-01-30",100)}},"2026-01-30")
if __name__=="__main__":unittest.main()
