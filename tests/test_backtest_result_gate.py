import unittest
from backtest_result_gate import evaluate

class GateTest(unittest.TestCase):
    def fixture(self,amount=500000):
        return {"status":"completed","paper_result":{
            "final_equity":amount,"validation_status":"PROVISIONAL_UNVERIFIED",
            "ledger_audit":{"audit":"INTERNAL_CASH_AND_QUANTITY_RECONCILED"},
            "valuation_diagnostics":{"final_equity_available":amount is not None}}}
    def test_incomplete_history_is_ci_failure(self):
        self.assertEqual(evaluate(self.fixture(None)),(False,"UNPRICED_FINAL_EQUITY"))
        self.assertEqual(evaluate({"status":"no_qualifying_train_rule"}),(False,"BACKTEST_DID_NOT_COMPLETE"))
    def test_provisional_not_verified(self):
        good,status=evaluate(self.fixture())
        self.assertTrue(good)
        self.assertIn("NOT_VERIFIED",status)
    def test_no_fabricated_value_accepted(self):
        for invalid in (float("nan"),float("inf"),-1,True):
            self.assertFalse(evaluate(self.fixture(invalid))[0])
    def test_missing_or_failed_cash_ledger_rejected(self):
        r=self.fixture()
        r["paper_result"].pop("ledger_audit")
        self.assertEqual(evaluate(r),(False,"ACCOUNTING_LEDGER_UNVERIFIED"))
        r["paper_result"]["ledger_audit"]={"audit":"FAILED"}
        self.assertFalse(evaluate(r)[0])

    def test_missing_diagnostic_rejected(self):
        r=self.fixture()
        r["paper_result"].pop("valuation_diagnostics")
        self.assertFalse(evaluate(r)[0])

if __name__=="__main__":unittest.main()
