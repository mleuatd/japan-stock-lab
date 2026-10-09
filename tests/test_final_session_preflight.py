import unittest
from final_session_preflight import FINAL_COVERAGE_SQL,summarize

class FinalSessionPreflightTest(unittest.TestCase):
    def test_reports_aggregate_risk(self):
        row=dict(last_day="2026-07-17",final_rows=4442,final_valid_closes=4218,
                 final_incomplete_rows=224,recent_symbols=4444)
        summary=summarize(row)
        self.assertEqual(summary["final_close_missing_or_invalid"],224)
        self.assertEqual(summary["recent_symbols_not_on_final_day"],2)
        self.assertTrue(summary["mark_to_market_risk"])
        self.assertEqual(summary["result"],"AGGREGATE_ONLY_NOT_PORTFOLIO_VERIFIED")
    def test_no_false_approval_of_portfolio(self):
        a=summarize(dict(last_day="2026-07-17",final_rows=5,final_valid_closes=5,
                         final_incomplete_rows=0,recent_symbols=5))
        self.assertFalse(a["mark_to_market_risk"])
        self.assertNotIn("VERIFIED_PORTFOLIO",a["result"])
    def test_sql_read_only_and_does_not_return_tickers(self):
        s=FINAL_COVERAGE_SQL.upper()
        self.assertIn("COUNT(DISTINCT SECURITY_CODE)",s)
        self.assertNotIn("GROUP BY SECURITY_CODE",s)
        self.assertNotIn("DELETE FROM",s)
        self.assertNotIn("UPDATE DAILY_BAR",s)

if __name__=="__main__":unittest.main()
