import unittest
from paper_ledger_accounting import reconcile
from february_walkforward import replay
from walkforward_backtest import Bar

class IndependentLedgerAuditTest(unittest.TestCase):
    def test_purchase_sale_tax_and_dividend(self):
        logs=[
            {"date":"2026-02-02","code":"A","side":"BUY","qty":100,"total_debit":10020.},
            {"date":"2026-02-03","code":"A","side":"ACTION","status":"DIVIDEND","net_credit":80.},
            {"date":"2026-02-04","code":"A","side":"SELL","qty":100,"net_credit":10800.}
        ]
        r=reconcile(500000,logs,{},500860.)
        self.assertEqual(r["executed_buys"],1)
        self.assertEqual(r["paid_dividends"],1)
        bad=[dict(x) for x in logs]
        bad[2]["net_credit"]=10700.
        with self.assertRaises(AssertionError):
            reconcile(500000,bad,{},500860.)
    def test_split_changes_quantity_not_cash(self):
        e=[{"date":"2026-02-02","code":"A","side":"BUY","qty":100,"total_debit":10000.},
           {"date":"2026-02-03","code":"A","side":"ACTION","status":"SPLIT","ratio":2,"qty":200}]
        r=reconcile(500000,e,{"A":{"qty":200}},490000.)
        self.assertEqual(r["applied_splits"],1)
        e[1]["qty"]=201
        with self.assertRaises(AssertionError):
            reconcile(500000,e,{"A":{"qty":201}},490000.)
    def test_actual_replay_returns_audited_balance(self):
        dates=[f"2025-{1+i//28:02d}-{1+i%28:02d}" for i in range(122)]
        data={d:{"11110":Bar(d,"11110",100.,100.,1000,100.)} for d in dates}
        r=replay(data,{"lookback":3,"min_return_pct":0,"min_volume":0},
                 cutoff=dates[119],start=dates[120],fee_rate=.001,allocation=10000)
        self.assertEqual(r["ledger_audit"]["audit"],"INTERNAL_CASH_AND_QUANTITY_RECONCILED")
        self.assertGreaterEqual(r["cash"],0)

if __name__=="__main__":
    unittest.main()
