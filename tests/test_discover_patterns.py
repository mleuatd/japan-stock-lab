import datetime as dt
import unittest
from discover_patterns import discover,signal_features,pattern_name,PATTERNS
from walkforward_backtest import Bar

class DiscoverPatternsTests(unittest.TestCase):
    def test_features_do_not_read_future(self):
        seq=[Bar(f"2025-01-{i+1:02d}","11110",100,100+i,1000,100+i) for i in range(9)]
        before=signal_features(seq,7)
        seq[8]=Bar(seq[8].date,"11110",999999,999999,999999,999999)
        self.assertEqual(before,signal_features(seq,7))
    def test_holdout_and_watchlist_only_latest_date(self):
        start=dt.date(2025,1,1);data={}
        for i in range(110):
            day=(start+dt.timedelta(days=i)).isoformat()
            v=100+(i%20)
            data[day]={"11110":Bar(day,"11110",v,v,100000,v),
                       "22220":Bar(day,"22220",v+1,v+1,100000,v+1)}
        r=discover(data,min_events=1)
        self.assertEqual(r["sessions"],110)
        self.assertEqual(r["holdout_boundaries"]["discovery"],sorted(data)[65])
        self.assertEqual(r["holdout_boundaries"]["validation"],sorted(data)[87])
        self.assertTrue(all(x["as_of"]==r["data_last_date"] for x in r["historical_date_watchlist"]))
        self.assertTrue(all(x["discovery"]["n"]>0 and x["validation"]["n"]>0 for x in r["selected_patterns"]))
    def test_insufficient_history(self):
        with self.assertRaises(ValueError):
            discover({})
if __name__=="__main__":unittest.main()
