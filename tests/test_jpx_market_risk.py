"""Point-in-time safety regression: known JPX warnings, no retroactive peek."""
import datetime as dt
import unittest

from jpx_market_risk import risk_as_of_close,risk_as_of_open,VERIFIED_RESTRICTIONS
from february_walkforward import replay
from nightly_paper_plan import build_plan
from walkforward_backtest import Bar,simulate

def bar(day,code,px=100):
    return Bar(day,code,px,px,100000,px,px,px)

class JpxMarketRiskTests(unittest.TestCase):
    def test_source_dated_risks_do_not_look_ahead(self):
        # Restrictions cannot be applied before the JPX notice existed.
        for code,before,on,after in (
            ("61730","2025-01-27","2025-01-28","2025-01-29"),
            ("17260","2026-02-03","2026-02-04","2026-02-05"),
            ("62010","2026-05-11","2026-05-12","2026-05-13")):
            self.assertFalse(risk_as_of_close(code,before))
            self.assertFalse(risk_as_of_open(code,before))
            self.assertTrue(risk_as_of_close(code,on))
            self.assertFalse(risk_as_of_open(code,on))
            self.assertTrue(risk_as_of_open(code,after))
        self.assertFalse(risk_as_of_close("72030","2026-10-10"))
        self.assertTrue(all(row.source_url.startswith("https://www.jpx.co.jp/")
                            for row in VERIFIED_RESTRICTIONS))
    def test_no_fake_quotes_after_delisting(self):
        self.assertTrue(risk_as_of_open("61730","2026-06-01"))
        self.assertTrue(risk_as_of_open("17260","2026-06-01"))
        self.assertTrue(risk_as_of_open("62010","2026-06-01"))
    def test_frozen_replay_does_not_buy_special_caution_stock(self):
        ds=["2026-01-26","2026-01-27","2026-01-28",
            "2026-01-29","2026-01-30","2026-02-02","2026-02-03"]
        data={d:{"61730":bar(d,"61730",100+i*3)} for i,d in enumerate(ds)}
        r=replay(data,{"lookback":3,"min_return_pct":-10,"min_volume":0},
                 cutoff="2026-01-30",start="2026-02-02")
        self.assertFalse(any(x["side"]=="BUY" for x in r["fills"]))
        self.assertEqual(r["cash"],500000)
        self.assertIsNotNone(r["equity"][-1]["total_equity"])
        self.assertEqual(r["listing_risk_screen"]["historical_universe_coverage"],"INCOMPLETE")
    def test_existing_holding_exits_next_open_after_publication(self):
        ds=["2026-01-26","2026-01-27","2026-01-28",
            "2026-01-29","2026-01-30","2026-02-02",
            "2026-02-03","2026-02-04","2026-02-05","2026-02-06"]
        data={d:{"17260":bar(d,"17260",100+i)} for i,d in enumerate(ds)}
        r=replay(data,{"lookback":3,"min_return_pct":-10,"min_volume":0},
                 cutoff="2026-01-30",start="2026-02-02",hold_days=100)
        buys=[x for x in r["fills"] if x["side"]=="BUY"]
        sells=[x for x in r["fills"] if x["side"]=="SELL"]
        self.assertEqual(buys[0]["date"],"2026-02-02")
        self.assertTrue(sells)
        self.assertEqual(sells[0]["date"],"2026-02-05")
        self.assertEqual(sells[0]["signal_reason"],"KNOWN_JPX_LISTING_RISK")
        self.assertFalse(any(x["side"]=="BUY" and x["date"]>"2026-02-04"
                             for x in r["fills"]))
    def test_no_fill_if_risk_exit_open_is_missing(self):
        ds=["2026-01-26","2026-01-27","2026-01-28",
            "2026-01-29","2026-01-30","2026-02-02",
            "2026-02-03","2026-02-04","2026-02-05","2026-02-06"]
        data={d:{"17260":bar(d,"17260",100+i)} for i,d in enumerate(ds)}
        # Another symbol supplies market sessions; risk stock disappears.
        for d in ds:data[d]["11110"]=bar(d,"11110")
        del data["2026-02-05"]["17260"]
        del data["2026-02-06"]["17260"]
        r=replay(data,{"lookback":3,"min_return_pct":-10,"min_volume":0},
                 cutoff="2026-01-30",start="2026-02-02",hold_days=100)
        # Exposure remains unknown unless a later observable sell really executes.
        self.assertIn("17260",r["held"])
        self.assertIsNone(r["final_equity"])
        self.assertTrue(any(x["side"]=="SELL" and x.get("status")=="NO_OPEN"
                            and x["code"]=="17260" for x in r["fills"]))
    def test_nightly_plan_does_not_propose_known_risk(self):
        dates=["2026-04-29","2026-04-30"]
        data={d:{"61730":bar(d,"61730",100+i)} for i,d in enumerate(dates)}
        r=build_plan(data,{"cash":500000,"holdings":{}},
                     {"lookback":1,"min_return_pct":0,"min_volume":1},
                     as_of="2026-04-30")
        self.assertFalse(any(x["side"]=="BUY_CASH" for x in r["orders"]))
    def test_basic_simulation_excludes_risk_known_at_close(self):
        ds=["2026-04-27","2026-04-28","2026-04-29","2026-04-30",
            "2026-05-01","2026-05-02"]
        data={d:{"61730":bar(d,"61730",100+i)} for i,d in enumerate(ds)}
        r=simulate(data,{"lookback":1,"min_return_pct":0,"min_volume":0},hold_days=3)
        self.assertEqual([e for e in r["fills"] if e["side"]=="BUY"],[])

if __name__=="__main__":
    unittest.main()
