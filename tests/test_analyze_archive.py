import csv,gzip,tempfile,unittest
from pathlib import Path
from analyze_archive import rankings

class RankingTests(unittest.TestCase):
    def test_returns_top_and_consecutive_streak(self):
        with tempfile.TemporaryDirectory() as folder:
            for date,values in [("2025-01-06",[("1111","100"),("2222","100")]),
                                ("2025-01-07",[("1111","110"),("2222","90")]),
                                ("2025-01-08",[("1111","121"),("2222","80")])]:
                file=Path(folder)/(date+".csv.gz")
                with gzip.open(file,"wt",encoding="utf-8",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=["Code","AdjC"]);writer.writeheader()
                    for code,price in values:writer.writerow({"Code":code,"AdjC":price})
            output=list(rankings(folder))
            self.assertEqual(len(output),3)
            self.assertEqual(output[1][1][0]["code"],"1111")
            self.assertEqual(output[2][1][0]["consecutive_top30"],2)
    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(list(rankings(folder)),[])
if __name__=="__main__":unittest.main()
