"""Historical paired-exit tests: chronology, intraday ambiguity and cash limits."""
import datetime as dt
import math
import unittest

from chart_bracket import (Bracket, paired_exit, complete_bar, backtest,
                           pattern_signals, compare, PATTERN_LOOKBACK, CONFIGS)
from fast_strategy_grid import prepare, BUY
from walkforward_backtest import Bar

def bar(day, opened=100, closed=100, high=103, low=97, code="11110", volume=100000):
    return Bar(day, code, opened, closed, volume, closed, high, low)

class BracketPriceTest(unittest.TestCase):
    def test_prices_and_validation(self):
        self.assertEqual(Bracket(5,10,10).prices(100),(95,110.00000000000001))
        for invalid in ((0,10,10),(5,0,10),(100,10,10),(5,10,0)):
            with self.assertRaises(ValueError):Bracket(*invalid)
    def test_ambiguous_bar_is_worst_case_stop(self):
        b=bar("2026-02-02",100,100,115,90)
        self.assertEqual(paired_exit(b,100,Bracket(5,10,10)),("STOP",95))
    def test_gap_down_below_stop_fills_at_open_not_stop(self):
        b=bar("2026-02-03",87,90,94,84)
        self.assertEqual(paired_exit(b,100,Bracket(5,10,10)),("STOP_GAP",87))
    def test_gap_up_above_target_fills_at_open(self):
        b=bar("2026-02-03",117,115,119,112)
        self.assertEqual(paired_exit(b,100,Bracket(5,10,10)),("TARGET_GAP",117))
    def test_single_target_hit(self):
        b=bar("2026-02-03",101,107,111,100)
        self.assertEqual(paired_exit(b,100,Bracket(5,10,10)),("TARGET",110.00000000000001))
    def test_no_high_low_disables_intraday_inference(self):
        b=Bar("2026-02-02","11110",100,100,10000,100)
        self.assertFalse(complete_bar(b))
        self.assertIsNone(paired_exit(b,100,Bracket()))

class ReplayTests(unittest.TestCase):
    def setUp(self):
        begin=dt.date(2025,1,1)
        self.days=[(begin+dt.timedelta(days=i)).isoformat() for i in range(50)]
        self.data={d:{"11110":bar(d,100+i,100+i,102+i,98+i)}
                   for i,d in enumerate(self.days)}
    def test_signal_at_close_only_buys_next_open(self):
        # Pattern 'momentum' after 20 sessions of increasing prices.
        dates,feats=prepare(self.data)
        sig=pattern_signals(self.data,dates,feats,25,"momentum")
        self.assertEqual(sig,["11110"])
        result=backtest(self.data,dates,feats,"momentum",Bracket(5,10,10),
                        dates[25],dates[30],initial=500000,per_position=100000,fee=0)
        buys=[e for e in result["fills"] if e["side"]=="BUY"]
        self.assertTrue(buys)
        self.assertEqual(buys[0]["date"],dates[25])  # Previous close signal.
        self.assertGreaterEqual(result["ending_cash"],0)
        self.assertEqual(result["validation_status"],"PROVISIONAL_UNVERIFIED")
    def test_future_change_does_not_change_past_fills(self):
        dates,feat=prepare(self.data)
        r=backtest(self.data,dates,feat,"momentum",Bracket(5,10,10),dates[25],dates[30])
        future={k:dict(v) for k,v in self.data.items()}
        for d in dates[31:]:
            future[d]={"11110":bar(d,400,400,405,395)}
        nd,nf=prepare(future)
        rr=backtest(future,nd,nf,"momentum",Bracket(5,10,10),nd[25],nd[30])
        self.assertEqual(r,rr)
    def test_missing_high_low_marks_unverified(self):
        dates,feat=prepare(self.data)
        at=dates[27]
        old=self.data[at]["11110"]
        self.data[at]["11110"]=Bar(at,"11110",old.open,old.close,100000,old.adj_close)
        r=backtest(self.data,dates,feat,"momentum",Bracket(5,10,20),dates[25],dates[35])
        self.assertGreater(r["missing_intraday_exposure_sessions"],0)
        self.assertIsNone(r["net_pnl"])
        self.assertFalse(r["priced_complete"])
    def test_sparse_history_cannot_trigger_pattern(self):
        dates,feat=prepare(self.data)
        self.data[dates[24]].pop("11110")
        nd,nf=prepare(self.data)
        self.assertEqual(pattern_signals(self.data,nd,nf,25,"momentum"),[])
    def test_135_configurations(self):
        self.assertEqual(len(BUY)*len(CONFIGS),135)
        self.assertEqual(PATTERN_LOOKBACK["momentum"],20)
    def test_same_day_ambiguous_exit_does_not_double_sell(self):
        dates,features=prepare(self.data)
        day=dates[25]
        self.data[day]["11110"]=bar(day,125,125,150,90)
        new_days,new_features=prepare(self.data)
        r=backtest(self.data,new_days,new_features,"momentum",Bracket(5,10,10),
                   dates[25],dates[25],initial=500000,fee=0)
        sales=[e for e in r["fills"] if e["side"]=="SELL"]
        self.assertEqual(len(sales),1)
        self.assertEqual(sales[0]["reason"],"STOP")
        self.assertGreaterEqual(r["ending_cash"],0)

if __name__=="__main__":
    unittest.main()
