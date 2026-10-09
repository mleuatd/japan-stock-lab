import unittest
from february_walkforward import replay
from walkforward_backtest import Bar


def bar(day, code, opened, closed=None, volume=100000):
    closed=opened if closed is None else closed
    return Bar(day,code,opened,closed,volume,closed)


class CorporateAccountingTests(unittest.TestCase):
    def setUp(self):
        self.data={}
        for n in range(122):
            day=f"2025-{1+(n//28):02d}-{1+n%28:02d}"
            self.data[day]={"11110":bar(day,100,100)}
        self.days=sorted(self.data)
        self.cutoff=self.days[119]
        self.start=self.days[120]
        self.rule={"lookback":3,"min_return_pct":0,"min_volume":0}

    def test_start_must_be_immediate_market_session(self):
        with self.assertRaises(ValueError):
            replay(self.data,self.rule,cutoff=self.days[118],start=self.days[120])

    def test_missing_final_held_close_does_not_fabricate_equity(self):
        last=self.days[-1]
        self.data[last].pop("11110")
        self.data[last]["22220"]=bar(last,"22220",150)
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=10000,hold_days=90,fee_rate=0)
        self.assertIsNone(r["final_equity"])
        self.assertIsNone(r["max_drawdown_pct"])

    def test_accounting_summary_and_missing_corporate_date(self):
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=10000,hold_days=90,fee_rate=0)
        self.assertEqual(r["final_equity"],500000)
        self.assertEqual(r["realized_pnl"],0)
        self.assertEqual(r["max_drawdown_pct"],0)
        with self.assertRaises(ValueError):
            replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   corporate_actions={"2099-01-01":{"11110":{"split_ratio":2}}})

    def test_dividend_requires_entitlement_and_does_not_pay_new_holder(self):
        payment=self.days[121]
        with self.assertRaises(ValueError):
            replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   corporate_actions={payment:{"11110":{"cash_dividend_per_share":10}}})
        result=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
               allocation=10000,hold_days=90,fee_rate=0,
               corporate_actions={payment:{"11110":{"cash_dividend_per_share":10,
                                                        "entitlement_date":self.cutoff}}})
        self.assertEqual(result["known_net_dividends"],0)

    def test_dividend_paid_after_sale_to_prior_entitled_holder(self):
        day=self.days[121]
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=10000,hold_days=1,fee_rate=0,
                 corporate_actions={day:{"11110":{"cash_dividend_per_share":10,
                                                      "entitlement_date":self.days[120]}}})
        self.assertEqual(r["known_net_dividends"],1000)

    def test_unrealized_profit_reconciles_to_cash_and_equity(self):
        day=self.days[-1]
        self.data[day]["11110"]=bar(day,"11110",110,110)
        result=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                      allocation=10000,hold_days=90,fee_rate=0)
        self.assertEqual(result["final_equity"],501000)
        self.assertEqual(result["unrealized_pnl"],1000)
        self.assertEqual(result["cash"],490000)
        self.assertEqual(result["realized_pnl"],0)

    def test_invalid_split_without_holding_is_rejected(self):
        day=self.days[120]
        with self.assertRaises(ValueError):
            replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   allocation=10000,hold_days=90,fee_rate=0,
                   corporate_actions={day:{"11110":{"split_ratio":0}}})

    def test_take_profit_exit_is_at_next_open_not_signal_close(self):
        day=self.days[121]
        self.data[day]["11110"]=bar(day,"11110",110,130)
        # The exit is queued on the final close, never filled on this day.
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=12000,hold_days=99,fee_rate=0,take_profit_pct=10)
        self.assertEqual(len([f for f in r["fills"] if f["side"]=="SELL"]),0)
        self.assertTrue(any(o["reason"]=="TAKE_PROFIT" for o in r["unfilled_after_final_session"]))

    def test_stop_loss_signal_is_after_close(self):
        day=self.days[121]
        self.data[day]["11110"]=bar(day,"11110",100,90)
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=12000,hold_days=99,fee_rate=0,stop_loss_pct=5)
        self.assertTrue(any(o["reason"]=="STOP_LOSS" for o in r["unfilled_after_final_session"]))

    def test_position_cap_and_threshold_validation(self):
        more={}
        for d,rows in self.data.items():
            more[d]={**rows,"22220":bar(d,"22220",100)}
        r=replay(more,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=12000,fee_rate=0,hold_days=99,max_positions=1)
        self.assertLessEqual(len(r["held"]),1)
        for kwargs in ({"max_positions":0},{"stop_loss_pct":-1},
                       {"take_profit_pct":float("inf")},
                       {"trailing_stop_pct":0}):
            with self.assertRaises(ValueError):
                replay(more,self.rule,cutoff=self.cutoff,start=self.start,**kwargs)

    def test_split_plus_dividend_after_sale_still_pays_entitled_holder(self):
        # First replay open buys, final day open sells. Split occurs when
        # no position remains at dividend *payment* time in real account.
        payment=self.days[121]
        event={"split_ratio":2,"cash_dividend_per_share":10,
               "entitlement_date":self.days[120]}
        res=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   allocation=10000,hold_days=1,fee_rate=0,
                   corporate_actions={payment:{"11110":event}})
        self.assertEqual(res["known_net_dividends"],1000)

    def test_trailing_stop_runs_on_close_and_queues_for_next_open(self):
        # Closing quote falls from previously established high, but is
        # never treated as the next opening execution price.
        day=self.days[121]
        self.data[day]["11110"]=bar(day,"11110",100,94)
        res=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   allocation=12000,hold_days=99,fee_rate=0,trailing_stop_pct=5)
        sells=[e for e in res["fills"] if e["side"]=="SELL"]
        self.assertFalse(sells)
        self.assertEqual(res["unfilled_after_final_session"][0]["reason"],"TRAILING_STOP")

    def test_split_preserves_cost_basis_and_no_negative_cash(self):
        # Existing January signal opens a 100-share position on the first test day.
        split_day=self.days[121]
        self.data[split_day]["11110"]=bar(split_day,50,50)
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=10000,hold_days=90,fee_rate=0,
                 corporate_actions={split_day:{"11110":{"split_ratio":2}}})
        self.assertEqual(r["held"]["11110"]["qty"],200)
        self.assertEqual(r["held"]["11110"]["cost"],10000)
        self.assertEqual(r["equity"][-1]["total_equity"],500000)
        self.assertGreaterEqual(r["cash"],0)

    def test_dividend_on_payment_date_and_tax(self):
        day=self.days[121]
        r=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                 allocation=10000,hold_days=90,fee_rate=0,tax_rate=.2,
                 corporate_actions={day:{"11110":{"cash_dividend_per_share":10,"entitlement_date":self.days[120]}}})
        self.assertEqual(r["cash"],490800)
        self.assertTrue(any(x.get("status")=="DIVIDEND" and x["net"]==800 for x in r["fills"]))

    def test_fractional_split_rejected_without_source(self):
        day=self.days[121]
        with self.assertRaises(ValueError):
            replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                   allocation=10000,hold_days=90,fee_rate=0,
                   corporate_actions={day:{"11110":{"split_ratio":1.005}}})

    def test_slippage_reduces_equity_and_preserves_cash(self):
        base=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                    allocation=12000,hold_days=90,fee_rate=0)
        worse=replay(self.data,self.rule,cutoff=self.cutoff,start=self.start,
                     allocation=12000,hold_days=90,fee_rate=0,slippage_rate=.01)
        self.assertLess(worse["equity"][-1]["total_equity"],base["equity"][-1]["total_equity"])
        self.assertGreaterEqual(worse["cash"],0)

if __name__=="__main__":
    unittest.main()
