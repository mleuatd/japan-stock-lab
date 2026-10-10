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
    def test_buy_candidate_contains_inactive_paired_exit_reference(self):
        r=build_plan(self.data,{"cash":30000,"holdings":{}},self.rule,"2026-10-07",
                     stop_pct=5,target_pct=10)
        buys=[o for o in r["orders"] if o["side"]=="BUY_CASH"]
        self.assertTrue(buys)
        for order in buys:
            paired=order["paired_sell_after_buy"]
            self.assertTrue(paired["reference_entry_is_not_actual_fill"])
            self.assertEqual(paired["activate"],"ONLY_AFTER_CONFIRMED_BUY_FILL")
            self.assertLess(paired["stop_trigger_reference"],order["reference_close"])
            self.assertGreater(paired["take_profit_limit_reference"],order["reference_close"])
            self.assertEqual(paired["qty_if_filled"],order["qty"])
    def test_held_shares_have_exact_qty_paired_preview(self):
        r=build_plan(self.data,{"cash":0,"holdings":{"72030":{
            "qty":200,"entry_price":100}}},self.rule,"2026-10-07")
        self.assertEqual(r["held_exit_templates"][0]["qty"],200)
        self.assertEqual(r["held_exit_templates"][0]["stop_trigger_reference"],95)
        self.assertEqual(r["held_exit_templates"][0]["take_profit_limit_reference"],110.0)
        self.assertTrue(r["held_exit_templates"][0]["not_executed"])
    def test_stale_history_has_no_bracket_order_preview(self):
        r=build_plan(self.data,{"cash":500000,"holdings":{"72030":{
            "qty":100,"entry_price":100}}},self.rule,"2026-11-15")
        self.assertEqual(r["held_exit_templates"],[])
        self.assertEqual(r["orders"],[])

    def test_no_negative_money_or_positions(self):
        data={"2026-10-06":{"72030":b("2026-10-06",price=100)},
              "2026-10-07":{"72030":b("2026-10-07",price=105)},
              "2026-10-08":{"72030":b("2026-10-08",price=150)}}
        r=simulate(data,{"lookback":1,"min_return_pct":2},initial_cash=500000,allocation=1)
        self.assertGreaterEqual(r["ending_cash"],0)
        self.assertTrue(all(x["side"] in ("BUY","SELL") for x in r["fills"]))
if __name__=="__main__":unittest.main()
