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
if __name__=="__main__":
    unittest.main()
