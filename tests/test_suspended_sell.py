import datetime as dt
import unittest
from february_walkforward import replay
from walkforward_backtest import Bar

class SuspendedSellTests(unittest.TestCase):
    def test_unfilled_sell_retries_without_fabricated_execution(self):
        dates=[(dt.date(2025,1,1)+dt.timedelta(days=i)).isoformat() for i in range(125)]
        data={d:{"11110":Bar(d,"11110",100,100,100000,100)} for d in dates}
        # Initial Jan-like close signal -> first test opening BUY.
        cutoff,start=dates[119],dates[120]
        data[dates[121]]={}  # no price available on planned sell session
        result=replay(data,{"lookback":3,"min_return_pct":0,"min_volume":0},
                      cutoff=cutoff,start=start,fee_rate=0,hold_days=1,allocation=10000)
        buys=[x for x in result["fills"] if x["side"]=="BUY"]
        sells=[x for x in result["fills"] if x["side"]=="SELL" and x.get("status")!="NO_OPEN"]
        missing=[x for x in result["fills"] if x.get("status")=="NO_OPEN" and x["side"]=="SELL"]
        self.assertTrue(buys)
        self.assertTrue(missing)
        self.assertEqual(sells[0]["date"],dates[122])
        self.assertEqual(sells[0]["signal_reason"],"MAX_HOLD")
        self.assertGreaterEqual(result["cash"],0)
        self.assertTrue(all(x["date"] != dates[121] for x in sells))

    def test_last_session_missing_open_preserves_unfilled_sell(self):
        dates=[(dt.date(2025,1,1)+dt.timedelta(days=i)).isoformat() for i in range(123)]
        data={d:{"11110":Bar(d,"11110",100,100,100000,100)} for d in dates}
        cutoff,start=dates[119],dates[120]
        data[dates[-1]]={}
        result=replay(data,{"lookback":3,"min_return_pct":0,"min_volume":0},
                      cutoff=cutoff,start=start,fee_rate=0,hold_days=1,allocation=10000)
        self.assertTrue(any(x["side"]=="SELL" for x in result["unfilled_after_final_session"]))
        self.assertIsNone(result["final_equity"])

if __name__=="__main__":unittest.main()
