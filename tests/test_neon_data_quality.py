import unittest
from neon_data_quality import summarize, QUERY

class QualityTest(unittest.TestCase):
    def fixture(self):
        return dict(total=100,first_date="2024-10-08",last_date="2026-10-09",
                    symbols=8,holdout_rows=35,nonunit_factor_rows=2,
                    holdout_nonunit_factor_rows=1,required_null_rows=4,
                    invalid_value_rows=0,holdout_required_null_rows=2,
                    holdout_invalid_value_rows=0)

    def test_invalid_rows_and_actions_are_not_certified(self):
        report=summarize(self.fixture(),today="2026-10-10")
        self.assertEqual(report["validation_status"],"PROVISIONAL_UNVERIFIED")
        self.assertIn("INVALID_OR_INCOMPLETE_BAR_ROWS",report["blocking_issues"])
        self.assertIn("CORPORATE_ACTION_RECONCILIATION_REQUIRED",report["blocking_issues"])
        self.assertEqual(report["holdout_nonunit_factor_rows"],1)

    def test_staleness_and_empty_holdout(self):
        row=self.fixture();row.update(last_date="2026-07-17",holdout_rows=0)
        report=summarize(row,today="2026-10-10")
        self.assertTrue(report["stale"])
        self.assertIn("STALE_DATA",report["blocking_issues"])
        self.assertIn("NO_HOLDOUT_DATA",report["blocking_issues"])

    def test_clean_archives_are_still_provisional(self):
        row=self.fixture()
        row.update(nonunit_factor_rows=0,holdout_nonunit_factor_rows=0,
                   required_null_rows=0,holdout_required_null_rows=0)
        report=summarize(row,today="2026-10-10")
        self.assertEqual(report["blocking_issues"],[])
        self.assertEqual(report["validation_status"],"PROVISIONAL_UNVERIFIED")

    def test_null_adjustment_factor_is_distinct_from_nonunit_factor(self):
        row=self.fixture()
        row.update(nonunit_factor_rows=0, holdout_nonunit_factor_rows=0,
                   null_factor_rows=3, missing_open_rows=2)
        result=summarize(row,today="2026-10-10")
        self.assertEqual(result["nonunit_factor_rows"],0)
        self.assertIn("UNKNOWN_ADJUSTMENT_FACTORS",result["blocking_issues"])
        self.assertNotIn("CORPORATE_ACTION_RECONCILIATION_REQUIRED",result["blocking_issues"])
        self.assertEqual(result["missing_required_field_counts"]["open"],2)

    def test_query_distinguishes_missing_from_nonunit_factors(self):
        normalized=" ".join(QUERY.upper().split())
        self.assertIn("ADJUSTMENT_FACTOR IS NULL",normalized)
        self.assertIn("ADJUSTMENT_FACTOR IS NOT NULL AND ADJUSTMENT_FACTOR <> 1",normalized)

    def test_query_only_reads_aggregate(self):
        normalized=QUERY.upper()
        self.assertEqual(normalized.count("%S"),4)
        self.assertIn("FROM DAILY_BAR",normalized)
        self.assertNotIn("DELETE ",normalized)
        self.assertNotIn("UPDATE ",normalized)
        self.assertNotIn("INSERT ",normalized)

if __name__=="__main__":
    unittest.main()
