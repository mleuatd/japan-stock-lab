import unittest
from p0_portfolio_audit import exposure_windows, summarize

class PortfolioAuditTests(unittest.TestCase):
    def test_exposure_windows(self):
        events=[
            {"date":"2026-02-02","code":"11110","side":"BUY","qty":100},
            {"date":"2026-02-03","code":"11110","side":"SELL","qty":100},
            {"date":"2026-02-04","code":"22220","side":"BUY","qty":100},
            {"date":"2026-02-05","code":"22220","side":"SELL","status":"NO_OPEN"}
        ]
        actual=exposure_windows(events,{"22220":{"qty":100}},"2026-02-06")
        self.assertEqual(actual,[("11110","2026-02-02","2026-02-03"),
                                 ("22220","2026-02-04","2026-02-06")])
    def test_invalid_ledger(self):
        with self.assertRaises(ValueError):
            exposure_windows([{"date":"2026-02-02","code":"X","side":"SELL","qty":100}],{},"2026-02-04")
        with self.assertRaises(ValueError):
            exposure_windows([{"date":"2026-02-02","code":"X","side":"BUY","qty":100}],{},"2026-02-04")
    def test_provisional_on_source_gap(self):
        result={"data_last_date":"2026-07-17","paper_result":{
            "held":{"X":{"qty":100}},"final_equity":None,
            "valuation_diagnostics":{"held_positions_without_final_close":1}}}
        source={"held":1,"absent_final_row":1,"invalid_final_close":0,
                "valid_raw_final_close":0,"valid_close_but_loader_excluded":0,
                "has_prior_valid_quote":1}
        factors={"unusual_factor_rows":2,"exposed_symbols_with_factor":1,
                 "unknown_factor_rows":0}
        report=summarize(result,source,factors,[("X","2026-02-02","2026-07-17")])
        self.assertEqual(report["validation_status"],"BLOCKED_EXTERNAL_DATA")
        self.assertFalse(report["formal_final_equity_available"])
    def test_final_gap_age_buckets_and_blockers(self):
        result={"data_last_date":"2026-07-17","paper_result":{
            "held":{"X":{"qty":100}},"final_equity":None,
            "valuation_diagnostics":{"held_positions_without_final_close":1}}}
        source={"held":1,"absent_final_row":1,"invalid_final_close":0,
                "valid_raw_final_close":0,"valid_close_but_loader_excluded":0,
                "has_prior_valid_quote":1}
        factors={"unusual_factor_rows":0,"exposed_symbols_with_factor":0,
                 "unknown_factor_rows":0}
        gaps={"missing_final_holdings":1,"no_prior_valid_close":0,
              "prior_close_age_0_to_7_days":0,
              "prior_close_age_8_to_30_days":1,
              "prior_close_age_over_30_days":0,
              "later_unpriced_rows_after_last_valid_close":1,
              "min_prior_close_age_days":12,"max_prior_close_age_days":12}
        report=summarize(result,source,factors,[("X","2026-02-02","2026-07-17")],gaps)
        self.assertEqual(report["validation_status"],"BLOCKED_EXTERNAL_DATA")
        self.assertEqual(report["missing_final_holding_gap_provenance"]["max_prior_close_age_days"],12)
        self.assertIn("HELD_FINAL_QUOTE_MISSING",report["blocking_reasons"])
        self.assertIn("CORPORATE_ACTION_AND_DELISTING_EVIDENCE_UNVERIFIED",report["blocking_reasons"])
        self.assertFalse(report["formal_final_equity_available"])
        gaps["prior_close_age_8_to_30_days"]=0
        with self.assertRaises(AssertionError):
            summarize(result,source,factors,[("X","2026-02-02","2026-07-17")],gaps)

if __name__=="__main__":
    unittest.main()
