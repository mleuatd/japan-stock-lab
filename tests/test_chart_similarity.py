"""Regression tests for screenshot curve matching and next-N-session outcomes."""
import datetime as dt
import math
import unittest
from chart_similarity import find_matches, fingerprint, rms_distance, wilson
from walkforward_backtest import Bar

def bar(day,code,px):
    return Bar(day,code,px,px,100000,px)

class ChartSimilarityTests(unittest.TestCase):
    def setUp(self):
        self.days=[(dt.date(2025,1,1)+dt.timedelta(days=i)).isoformat()
                   for i in range(121)]
        self.data={}
        for i,d in enumerate(self.days):
            # Every 40 sessions distinct pattern and forward return.
            price=100+i%40 + (0 if i<80 else 3)
            self.data[d]={"11110":bar(d,"11110",price),
                          "22220":bar(d,"22220",220-price/2)}
    def test_scale_and_shift_invariance(self):
        base=fingerprint([5,7,4,8,12],count=20)
        transformed=fingerprint([v*3+250 for v in [5,7,4,8,12]],count=20)
        self.assertLess(rms_distance(base,transformed),1e-10)
    def test_reject_flat_and_bad_inputs(self):
        with self.assertRaises(ValueError): fingerprint([1,1,1])
        with self.assertRaises(ValueError): fingerprint([1,math.nan,3])
    def test_wilson_interval(self):
        lo,hi=wilson(7,10)
        self.assertLess(lo,70)
        self.assertGreater(hi,70)
        self.assertIsNone(wilson(0,0))
    def test_all_examples_have_fully_observed_future(self):
        ref=[100+i for i in range(20)]
        r=find_matches(self.data,ref,lookback=20,horizons=(5,10,20),top_k=30)
        self.assertTrue(r["independent_matches"]>0)
        for x in r["matches"]:
            i=self.days.index(x["match_date"])
            self.assertLessEqual(i+20,len(self.days)-1)
            self.assertEqual(sorted(x["future_returns_pct"]),["10","20","5"])
        self.assertEqual(r["status"],"HISTORICAL_DESCRIPTIVE_ONLY")
        for h in ("5","10","20"):
            s=r["statistics"][h]
            self.assertEqual(s["up"]+s["down"]+s["flat"],s["samples"])
            self.assertEqual(s["samples"],r["independent_matches"])
    def test_decluster_overlapping_patterns_by_code(self):
        r=find_matches(self.data,[100+i for i in range(20)],
                       lookback=20,horizons=(5,10,20),top_k=50)
        for code in ("11110","22220"):
            positions=[self.days.index(x["match_date"]) for x in r["matches"]
                       if x["code"]==code]
            for i,a in enumerate(positions):
                self.assertTrue(all(abs(a-b)>=40 for b in positions[i+1:]))
    def test_future_perturbation_cannot_change_known_past(self):
        ref=[100+i for i in range(20)]
        base=find_matches(self.data,ref,lookback=20,horizons=(5,10),
                          top_k=12,as_of=self.days[79])
        new_data={d:dict(bars) for d,bars in self.data.items()}
        for day in self.days[80:]:
            new_data[day]={"11110":bar(day,"11110",9999),
                           "22220":bar(day,"22220",1)}
        modified=find_matches(new_data,ref,lookback=20,horizons=(5,10),
                              top_k=12,as_of=self.days[79])
        self.assertEqual(base,modified)
    def test_missing_market_day_is_not_stitched_together(self):
        altered={d:dict(bars) for d,bars in self.data.items()}
        for d in self.days:
            if self.days.index(d)%2:
                altered[d].pop("11110")
        r=find_matches(altered,[100+i for i in range(20)],
                       lookback=20,horizons=(5,),top_k=10)
        self.assertTrue(all(x["code"]!="11110" for x in r["matches"]))
    def test_reference_symbol_can_be_excluded(self):
        r=find_matches(self.data,[100+i for i in range(20)],
                       lookback=20,horizons=(5,),top_k=10,
                       skip_code="11110")
        self.assertTrue(all(x["code"]!="11110" for x in r["matches"]))
    def test_limited_archive_rejects_nonexistent_horizon(self):
        with self.assertRaises(ValueError):
            find_matches({d:self.data[d] for d in self.days[:22]},
                         [100+i for i in range(20)],lookback=20,horizons=(20,))
if __name__=="__main__":
    unittest.main()
