import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from personal_fund_local_backup import safe_output_path, svg_chart, save_sqlite

class PersonalFundOfflineReportTests(unittest.TestCase):
    def test_refuse_public_repository_write(self):
        repo=Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError):
            safe_output_path(repo/"private_data",repo)
        with tempfile.TemporaryDirectory() as tmp:
            safe=safe_output_path(tmp,repo)
            self.assertEqual(safe,Path(tmp).resolve())

    def test_svg_uses_only_given_historical_data_and_has_description(self):
        columns=["month_key","invested_yen","market_value_yen","pnl_yen"]
        rows=[["2020-01-01",100,115,15],["2021-01-01",200,240,40]]
        svg=svg_chart(columns,rows)
        self.assertIn('<desc>',svg)
        self.assertIn('2021-01',svg)
        self.assertIn('240',svg)
        self.assertNotIn('DATABASE_URL',svg)
        with self.assertRaises(ValueError):
            svg_chart(["bad"],[[1]])

    def test_private_sqlite_export_has_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp=Path(tmp)/"back.sqlite3"
            save_sqlite(fp,{"private_test":(["fund_code","amount"],[["SYNTH",500],["MOCK",300]])})
            with sqlite3.connect(fp) as con:
                self.assertEqual(con.execute('SELECT SUM(CAST(amount AS INTEGER)) FROM private_test').fetchone()[0],800)

if __name__=="__main__":
    unittest.main()
