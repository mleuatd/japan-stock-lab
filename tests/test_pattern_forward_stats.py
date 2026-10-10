import datetime as dt
import unittest

from pattern_forward_stats import (
    COOLDOWN, DEFINITIONS, HORIZONS, analyze, detect, update_symbol,
    new_counter, report, wilson
)
from walkforward_backtest import Bar
from collections import defaultdict

def build_data(count=115, missing=None, code="11110"):
    start=dt.date(2025,7,1)
    days=[(start+dt.timedelta(days=i)).isoformat() for i in range(count)]
    data={}
    for i,day in enumerate(days):
        price=100+(i%17)
        if missing is not None and i==missing:
            data[day]={"88880":Bar(day,"88880",200,200,1000,200)}
        else:
            data[day]={
                code:Bar(day,code,price,price,1000,price),
                "88880":Bar(day,"88880",200,200,1000,200)}
    return days,data

class PatternHorizonTests(unittest.TestCase):
    def test_canonical_patterns(self):
        inc=[100+i for i in range(21)]
        rev=list(reversed(inc))
        up=detect(inc,[100]*21)
        down=detect(rev,[100]*21)
        self.assertIn("BASE",up)
        self.assertIn("UP3",up)
        self.assertIn("UP5",up)
        self.assertIn("HIGH20",up)
        self.assertNotIn("DOWN3",up)
        self.assertIn("DOWN3",down)
        self.assertIn("DOWN5",down)
        self.assertIn("LOW20",down)
        self.assertIn("SMA_BEAR",down)
    def test_volumes(self):
        series=[100]*20+[103]
        vols=[100]*20+[250]
        self.assertIn("VOL_UP",detect(series,vols))
        self.assertNotIn("VOL_DOWN",detect(series,vols))
        self.assertEqual(detect(series,[100]*20+[0]),())
    def test_invalid_points_are_not_signals(self):
        self.assertEqual(detect([100]*20+[float("nan")],[100]*21),())
        with self.assertRaises(ValueError):detect([100]*20,[100]*20)
    def test_all_30_horizons_and_empty_pattern_rows(self):
        days,data=build_data()
        result=analyze(data,train_end=days[63],holdout_start=days[64])
        self.assertEqual(HORIZONS,tuple(range(1,31)))
        self.assertEqual(len(result["stats"]),len(DEFINITIONS)*30*2)
        self.assertEqual(result["validation_status"],"PROVISIONAL_CORPORATE_ACTIONS_UNVERIFIED")
        self.assertEqual({r["trading_days_after"] for r in result["stats"]},set(HORIZONS))
        self.assertTrue(any(r["pattern_code"]=="DOWN5" for r in result["stats"]))
    def test_observed_down_up_flat_sum_consistency(self):
        days,data=build_data()
        res=analyze(data,train_end=days[63],holdout_start=days[64])
        for r in res["stats"]:
            self.assertEqual(r["observed"],r["up"]+r["down"]+r["flat"])
            self.assertEqual(r["events"],r["observed"]+r["missing"]+r["unmatured"])
            if r["observed"]==0:self.assertIsNone(r["up_pct"])
    def test_unmatured_is_not_counted_as_failure(self):
        days,data=build_data()
        res=analyze(data,train_end=days[63],holdout_start=days[64])
        train30=[r for r in res["stats"] if r["segment"]=="train"
                 and r["pattern_code"]=="BASE" and r["trading_days_after"]==30][0]
        self.assertGreater(train30["unmatured"],0)
        self.assertNotEqual(train30["events"],train30["observed"])
    def test_missing_next_market_session_is_missing_not_shifted(self):
        days,data=build_data(130,missing=31)
        res=analyze(data,train_end=days[69],holdout_start=days[70])
        one=[r for r in res["stats"] if r["segment"]=="train"
             and r["pattern_code"]=="BASE" and r["trading_days_after"]==1][0]
        self.assertGreater(one["missing"],0)
    def test_training_never_uses_prices_after_cutoff(self):
        days,data=build_data(125)
        a=analyze(data,train_end=days[69],holdout_start=days[70])
        changed={d:dict(rows) for d,rows in data.items()}
        for d in days[70:]:
            b=changed[d]["11110"]
            changed[d]["11110"]=Bar(d,"11110",9000,9000,1000,9000)
        b=analyze(changed,train_end=days[69],holdout_start=days[70])
        a_train=[x for x in a["stats"] if x["segment"]=="train"]
        b_train=[x for x in b["stats"] if x["segment"]=="train"]
        self.assertEqual(a_train,b_train)
    def test_cooldown_deduplicates_same_security_patterns(self):
        days,data=build_data(120)
        obs=[(i,100+i,1000) for i in range(120)]
        stats=defaultdict(new_counter)
        events=update_symbol("11110",obs,days,days[89],days[90],stats)
        baseline=[r for r in stats.items() if r[0][1]=="BASE" and r[0][2]==1]
        self.assertTrue(baseline)
        # At most three BASE events per segment over 120 daily observations.
        self.assertLessEqual(sum(v["observed"]+v["unmatured"] for _,v in baseline),4)
        self.assertGreater(events,0)
    def test_known_listing_risk_symbols_excluded_after_notice(self):
        days=[(dt.date(2026,5,1)+dt.timedelta(days=i)).isoformat() for i in range(90)]
        totals=defaultdict(new_counter)
        obs=[(i,100+i,1000) for i in range(len(days))]
        events=update_symbol("61730",obs,days,days[50],days[51],totals)
        self.assertEqual(events,0)
    def test_wilson_interval_bounds(self):
        low,hi=wilson(70,100)
        self.assertLess(low,70)
        self.assertGreater(hi,70)
        self.assertEqual(wilson(0,0),(None,None))
        self.assertEqual(COOLDOWN,30)

if __name__=="__main__":
    unittest.main()
