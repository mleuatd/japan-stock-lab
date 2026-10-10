"""V2 downside-first pattern and adverse excursion regression tests."""
import datetime as dt
import math
import unittest

from downside_pattern_research import (
    CATALOG, VERSION, analyze, adjusted, detect, count_outcomes, blank,
    summarize, wilson
)
from collections import defaultdict


def bar(p=100,vol=1000,lo=None,hi=None,op=None):
    op=p if op is None else op
    low=min(p,op)-1 if lo is None else lo
    high=max(p,op)+1 if hi is None else hi
    return {"adjusted_close":p,"close_price":p,"volume":vol,
            "open_price":op,"high_price":high,"low_price":low}


def sessions(n=120):
    base=dt.date(2025,1,1)
    return [(base+dt.timedelta(days=i)).isoformat() for i in range(n)]


class DownsidePatternV2Tests(unittest.TestCase):
    def test_catalog_is_large_and_deterministically_declared(self):
        self.assertGreaterEqual(len(CATALOG),110)
        self.assertEqual(VERSION,"downside-conditions-v2")
        self.assertIn("MA_BULL_HIGH20",CATALOG)
        self.assertIn("BEAR_ENGULF",CATALOG)
        self.assertIn("R20_DOWN10",CATALOG)
        self.assertNotIn("R20_DOWN99",CATALOG)

    def test_no_artificial_fitting_to_every_pattern(self):
        rising=[bar(100+i,1000) for i in range(21)]
        tags=detect(rising)
        self.assertIn("HIGH20",tags)
        self.assertIn("STREAK3_UP",tags)
        self.assertIn("MA5_20_BULL",tags)
        self.assertIn("MA_BULL_HIGH20",tags)
        self.assertNotIn("LOW20",tags)
        self.assertNotIn("STREAK3_DOWN",tags)
        self.assertNotIn("BEAR_BODY",tags)
        self.assertLess(len(tags),len(CATALOG)/2)

    def test_insufficient_window_or_price_refused(self):
        with self.assertRaises(ValueError):detect([bar() for _ in range(20)])
        b=[bar(100+i) for i in range(21)]
        b[-1]["adjusted_close"]=float("nan")
        self.assertEqual(detect(b),set())

    def test_adjusted_intraday_levels_same_scale_as_price(self):
        b={"adjusted_close":100,"close_price":300,
           "open_price":303,"high_price":312,"low_price":270,"volume":1000}
        result=adjusted(b)
        self.assertAlmostEqual(result[2],101)
        self.assertAlmostEqual(result[3],104)
        self.assertAlmostEqual(result[4],90)

    def test_missing_ohlc_does_not_manufacture_candlesticks(self):
        b=[bar(100+i) for i in range(21)]
        b[-1]["high_price"]=None
        tags=detect(b)
        self.assertIn("HIGH20",tags)
        self.assertNotIn("UPPER_WICK",tags)
        self.assertNotIn("CLOSE_HIGH",tags)
        self.assertNotIn("GAP_UP",tags)

    def test_next_day_flat_close_but_five_percent_intraday_loss(self):
        dates=sessions(45)
        data={i:bar(100) for i in range(45)}
        data[21]=bar(100,lo=94,hi=101)
        records=list(data.items())
        totals=defaultdict(blank)
        uniques=defaultdict(set)
        count_outcomes(totals,"11110",records,dates,dates[35],dates[36],uniques)
        k=totals[("train","BASE",1)]
        self.assertEqual(k["observed"],1)
        self.assertEqual(k["flat"],1)
        self.assertEqual(k["down"],0)
        self.assertEqual(k["path_complete"],1)
        self.assertEqual(k["touch3"],1)
        self.assertEqual(k["touch5"],1)
        self.assertEqual(k["touch10"],0)

    def test_missing_future_quote_does_not_count_as_down(self):
        dates=sessions(46)
        observations=[(i,bar(100)) for i in range(46) if i!=21]
        totals=defaultdict(blank);symbols=defaultdict(set)
        count_outcomes(totals,"11110",observations,dates,dates[35],dates[36],symbols)
        day1=totals[("train","BASE",1)]
        self.assertEqual(day1["missing"],1)
        self.assertEqual(day1["down"],0)
        self.assertEqual(day1["observed"],0)

    def test_missing_intraday_high_low_disables_path_probability(self):
        dates=sessions(48)
        obs=[(i,bar(100)) for i in range(48)]
        obs[21][1]["low_price"]=None
        total=defaultdict(blank);sym=defaultdict(set)
        count_outcomes(total,"11110",obs,dates,dates[35],dates[36],sym)
        a=total[("train","BASE",1)]
        self.assertEqual(a["observed"],1)
        self.assertEqual(a["path_unknown"],1)
        self.assertEqual(a["path_complete"],0)

    def test_no_train_future_leakage(self):
        dates=sessions(128)
        original={d:{"11110":bar(100+i%17)} for i,d in enumerate(dates)}
        before=analyze(original,dates[70],dates[71])
        change={day:dict(vals) for day,vals in original.items()}
        for day in dates[71:]:
            change[day]={"11110":bar(9000)}
        after=analyze(change,dates[70],dates[71])
        one=[x for x in before["rows"] if x["segment"]=="train"]
        two=[x for x in after["rows"] if x["segment"]=="train"]
        self.assertEqual(one,two)

    def test_all_30_days_and_minimum_sample_gate(self):
        dates=sessions(95)
        data={d:{"11110":bar(100+i%17)} for i,d in enumerate(dates)}
        r=analyze(data,dates[50],dates[51])
        self.assertEqual(len(r["rows"]),len(CATALOG)*30*2)
        self.assertEqual({x["horizon"] for x in r["rows"]},set(range(1,31)))
        self.assertEqual({x["state"] for x in r["rows"]},{"INSUFFICIENT_EVIDENCE"})
        for x in r["rows"]:
            self.assertEqual(x["total"],x["observed"]+x["missing"]+x["unmatured"])
            self.assertEqual(x["observed"],x["up"]+x["down"]+x["flat"])

    def test_wilson_bounds_and_no_observation(self):
        self.assertEqual(wilson(0,0),(None,None))
        self.assertLess(wilson(60,100)[0],60)
        self.assertGreater(wilson(60,100)[1],60)

    def test_known_jpx_warning_exclusion(self):
        dates=[(dt.date(2026,5,1)+dt.timedelta(days=i)).isoformat() for i in range(55)]
        r=analyze({day:{"61730":bar(100+i)} for i,day in enumerate(dates)},
                  dates[39],dates[40])
        self.assertTrue(all(x["total"]==0 for x in r["rows"]))

if __name__=="__main__":
    unittest.main()
