import unittest
from walkforward_backtest import Bar, simulate

def bar(d,code="11110",o=100,c=100,vol=1000):
    return Bar(d,code,o,c,vol,c)

class PointInTimeTests(unittest.TestCase):
    def test_signal_day_cannot_fill_until_next_open(self):
        data={
            "2025-01-01":{"11110":bar("2025-01-01",c=100)},
            "2025-01-02":{"11110":bar("2025-01-02",o=105,c=110)},
            "2025-01-03":{"11110":bar("2025-01-03",o=150,c=140)},
            "2025-01-06":{"11110":bar("2025-01-06",o=130,c=125)}
        }
        r=simulate(data,{"lookback":1,"min_return_pct":5},initial_cash=300000,allocation=1,hold_days=1,lot_size=1)
        first=r["fills"][0]
        self.assertEqual((first["date"],first["side"],first["price"]),("2025-01-03","BUY",150))
        self.assertNotIn("2025-01-02",[x["date"] for x in r["fills"] if x["side"]=="BUY"])
    def test_final_day_signal_has_no_fabricated_future_fill(self):
        data={"2025-01-01":{"11110":bar("2025-01-01",c=100)},
              "2025-01-02":{"11110":bar("2025-01-02",c=110)}}
        r=simulate(data,{"lookback":1,"min_return_pct":5})
        self.assertEqual(r["fills"],[])
        self.assertEqual(r["unfilled_last_day_orders"],[{"side":"BUY","code":"11110"}])
    def test_missing_next_open_is_skipped(self):
        data={"2025-01-01":{"11110":bar("2025-01-01",c=100)},
              "2025-01-02":{"11110":bar("2025-01-02",c=110)},
              "2025-01-03":{"22220":bar("2025-01-03",code="22220")}}
        r=simulate(data,{"lookback":1,"min_return_pct":5})
        self.assertTrue(any(e["action"]=="SKIP_NO_OPEN" for e in r["events"]))
        self.assertEqual(r["fills"],[])
    def test_fee_and_lot_are_applied(self):
        data={"2025-01-01":{"11110":bar("2025-01-01",c=100)},
              "2025-01-02":{"11110":bar("2025-01-02",c=110)},
              "2025-01-03":{"11110":bar("2025-01-03",o=120,c=120)}}
        r=simulate(data,{"lookback":1,"min_return_pct":5},initial_cash=10000,allocation=1,fee_pct=.01,lot_size=10)
        fill=r["fills"][0]
        self.assertEqual(fill["qty"]%10,0)
        self.assertLessEqual(fill["qty"]*fill["price"]*1.01,10000)
if __name__=="__main__": unittest.main()
