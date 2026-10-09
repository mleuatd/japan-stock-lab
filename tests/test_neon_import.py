import csv
import gzip
import tempfile
import unittest
from pathlib import Path
from neon_import import decode_day, checksum, source_fetched_at, COLUMNS

class ImportTests(unittest.TestCase):
    def make_file(self, rows):
        self.temp = tempfile.TemporaryDirectory()
        p=Path(self.temp.name)/"2025-01-06.csv.gz"
        with gzip.open(p,"wt",encoding="utf-8",newline="") as f:
            w=csv.writer(f)
            w.writerow(COLUMNS)
            w.writerows(rows)
        return p
    def tearDown(self):
        if hasattr(self,"temp"):
            self.temp.cleanup()
    def test_valid_day(self):
        p=self.make_file([["2025-01-06","7203","1","2","1","2","100","200","2","1"]])
        day,rows=decode_day(p)
        self.assertEqual((day,len(rows),rows[0][1]),("2025-01-06",1,"7203"))
        self.assertEqual(len(checksum(p)),64)
    def test_decimal_volume_is_normalized(self):
        p=self.make_file([["2025-01-06","7203","1","2","1","2","22200.0","200","2","1"]])
        _,rows=decode_day(p)
        self.assertEqual(rows[0][6],22200)
        self.assertIsInstance(rows[0][6],int)
    def test_fractional_volume_is_rejected(self):
        p=self.make_file([["2025-01-06","7203","1","2","1","2","22200.5","200","2","1"]])
        with self.assertRaises(ValueError):decode_day(p)
    def test_fetch_timestamp_from_sidecar(self):
        p=self.make_file([["2025-01-06","7203","1","2","1","2","100","200","2","1"]])
        self.assertIsNone(source_fetched_at(p))
        sidecar=p.with_name(p.name+".fetch.json")
        sidecar.write_text('{"fetched_at":"2026-10-09T01:00:00+00:00"}')
        stamp=source_fetched_at(p)
        self.assertEqual(stamp.isoformat(),"2026-10-09T01:00:00+00:00")
    def test_duplicate_code_rejected(self):
        row=["2025-01-06","7203","1","2","1","2","100","200","2","1"]
        p=self.make_file([row,row])
        with self.assertRaises(ValueError):decode_day(p)
    def test_mismatched_date_rejected(self):
        p=self.make_file([["2025-01-07","7203","1","2","1","2","100","200","2","1"]])
        with self.assertRaises(ValueError):decode_day(p)

if __name__=="__main__": unittest.main()
