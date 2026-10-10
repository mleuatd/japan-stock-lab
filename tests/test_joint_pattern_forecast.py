import datetime as dt
import unittest
from joint_pattern_forecast import (
    PATTERN_SQL,choose_patterns,build_sql,detect_recent,summarize
)
from pattern_forward_stats import DEFINITIONS

class JointPatternForecastTest(unittest.TestCase):
    def test_screens_same_pair_as_pilot_example(self):
        prices=[
            2027,2024.5,2028,2030.5,2090,2100,2116.5,2146.5,2115,
            2137,2155.5,2129.5,2127,2100,2110.5,2101.5,2108,
            2138.5,2119,2133,2173.5]
        volumes=[289300,289700,287900,363600,390700,284600,308000,
                 352600,411600,360300,310200,333800,347700,327800,
                 313500,292000,246700,215600,312400,317400,265100]
        dates=[
          "2026-09-08","2026-09-09","2026-09-10","2026-09-11",
          "2026-09-14","2026-09-15","2026-09-16","2026-09-17",
          "2026-09-18","2026-09-24","2026-09-25","2026-09-28",
          "2026-09-29","2026-09-30","2026-10-01","2026-10-02",
          "2026-10-05","2026-10-06","2026-10-07","2026-10-08","2026-10-09"]
        bars=[{"date":day,"adjusted_close":price,"volume":vol}
              for day,price,vol in zip(dates,prices,volumes)]
        found,close=detect_recent(bars,"2026-10-09")
        self.assertEqual(found,["HIGH20","SMA_BULL"])
        self.assertEqual(close,2173.5)
    def test_all_patterns_have_safe_sql_fragments(self):
        self.assertEqual(set(PATTERN_SQL),set(DEFINITIONS))
        self.assertEqual(choose_patterns(["SMA_BULL","HIGH20","BASE","HIGH20"]),
                         ["HIGH20","SMA_BULL"])
        query=build_sql(["HIGH20","SMA_BULL"])
        self.assertIn("adj>max_prev20",query)
        self.assertIn("avg5>avg20",query)
        self.assertIn("GENERATE_SERIES(1,30)",query)
        self.assertIn("idx-prev_idx=20",query)
        self.assertEqual(query.count("%s"),5)
        self.assertNotIn("2026-10-09",query)
        for injection in ("select 1;","HIGH20;DROP TABLE daily_bar;","UNKNOWN"):
            with self.assertRaises(ValueError):build_sql([injection])
    def test_pilot_sample_projection_and_counts(self):
        rows=[]
        for h in range(1,31):
            rows.append((h,10000,8500,1400,100,3800,4650,50,
                         -.18,-2.4685,-8.3,3.98))
        result=summarize(rows,["HIGH20","SMA_BULL"],2173.5,
                         "2026-10-09","2026-02-02","2026-07-17")
        self.assertEqual(len(result["days"]),30)
        last=result["days"][-1]
        self.assertEqual(last["scenario_median_yen"],2119.83)
        self.assertEqual(last["observed_examples"],8500)
        self.assertEqual(last["up_fraction_pct"],round(3800*100/8500,3))
        self.assertTrue(result["status"].startswith("PROVISIONAL"))
    def test_missing_and_unmatured_are_not_in_denominator(self):
        rows=[(h,10,5,3,2,2,2,1,.5,-.2,-1.5,2.1) for h in range(1,31)]
        r=summarize(rows,["UP3"],100,"2026-10-09","2026-02-02","2026-07-17")
        self.assertEqual(r["days"][0]["up_fraction_pct"],40)
        self.assertEqual(r["days"][0]["sample_status"],"INSUFFICIENT")
        self.assertEqual(r["days"][0]["scenario_median_yen"],99.8)
    def test_inconsistent_counts_refused(self):
        rows=[(h,10,5,4,2,1,2,2,.5,-.2,-1.5,2.1) for h in range(1,31)]
        with self.assertRaises(AssertionError):
            summarize(rows,["UP3"],100,"2026-10-09","2026-02-02","2026-07-17")
    def test_reference_dates_required(self):
        data=[{"date":(dt.date(2026,9,1)+dt.timedelta(days=i)).isoformat(),
               "adjusted_close":100+i,"volume":1000} for i in range(21)]
        with self.assertRaises(ValueError):detect_recent(data,"2026-10-09")
        with self.assertRaises(ValueError):detect_recent(data[::-1],data[0]["date"])
        with self.assertRaises(ValueError):detect_recent(data[:20],data[-1]["date"])

if __name__=="__main__":
    unittest.main()
