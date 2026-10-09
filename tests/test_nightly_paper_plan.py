import unittest
from nightly_paper_plan import build_plan
from walkforward_backtest import Bar,simulate

def b(date,code="72030",price=100,vol=1000000):
    return Bar(date,code,price,price,vol,price)

class NightlyPaperRules(unittest.TestCase):
    def setUp(self):
        self.data={
          "2026-10-06":{"72030":b("2026-10-06",price=100),"11110":b("2026-10-06",code="11110",price=200)},
          "2026-10-07":{"72030":b("2026-10-07",price=103),"11110":b("2026-10-07",code="11110",price=220)}}
        self.rule={"lookback":1,"min_return_pct":1,"min_volume":1,
                   "max_new_position_yen":20000,"max_hold_calendar_days":1}
    def test_stale_data_produces_no_orders(self):
        r=build_plan(self.data,{"cash":500000,"holdings":{ }},self.rule,"2026-10-20")
        self.assertTrue(r["stale"])
        self.assertEqual(r["orders"],[])
    def test_cannot_sell_unheld_shares_and_cannot_exceed_cash(self):
        r=build_plan(self.data,{"cash":30000,"holdings":{}},self.rule,"2026-10-07")
        self.assertTrue(all(x["side"]=="BUY_CASH" for x in r["orders"]))
        self.assertLessEqual(sum(x["estimated_cost"] for x in r["orders"]),30000)
        self.assertTrue(all(x["qty"]%100==0 for x in r["orders"]))
    def test_only_held_shares_sell(self):
        r=build_plan(self.data,{"cash":0,"holdings":{"72030":{"qty":200,"entry_price":100,"purchased_on":"2026-10-06"}}},self.rule,"2026-10-07")
        self.assertEqual([(x["code"],x["qty"]) for x in r["orders"] if x["side"]=="SELL_HELD"],[("72030",200)])
    def test_no_negative_money_or_positions(self):
        data={"2026-10-06":{"72030":b("2026-10-06",price=100)},
              "2026-10-07":{"72030":b("2026-10-07",price=105)},
              "2026-10-08":{"72030":b("2026-10-08",price=150)}}
        r=simulate(data,{"lookback":1,"min_return_pct":2},initial_cash=500000,allocation=1)
        self.assertGreaterEqual(r["ending_cash"],0)
        self.assertTrue(all(x["side"] in ("BUY","SELL") for x in r["fills"]))
if __name__=="__main__":unittest.main()
