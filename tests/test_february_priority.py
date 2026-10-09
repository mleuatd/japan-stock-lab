"""Regression: cash constrained entries must rank observed signal, not stock code."""
import datetime as dt
import unittest
from february_walkforward import replay
from walkforward_backtest import Bar


class BuyPriorityTest(unittest.TestCase):
    def test_stronger_signal_wins_one_slot(self):
        data = {}
        first = dt.date(2025, 9, 1)
        for i in range(130):
            day = (first + dt.timedelta(days=i)).isoformat()
            # Alphabetically earlier 11110 rises slowly, 99990 rises faster.
            data[day] = {
                "11110": Bar(day, "11110", 900 + i, 900 + i, 100000, 900 + i),
                "99990": Bar(day, "99990", 900 + 4*i, 900 + 4*i, 100000, 900 + 4*i),
            }
        cutoff = sorted(data)[120]
        start = sorted(data)[121]
        result = replay(
            data, {"lookback": 3, "min_return_pct": 0, "min_volume": 0},
            cutoff=cutoff, start=start, initial=500000,
            allocation=160000, lot=100, hold_days=100,
        )
        first_buy = next(x for x in result["fills"] if x["side"] == "BUY")
        self.assertEqual(first_buy["code"], "99990")
        self.assertGreaterEqual(result["cash"], 0)

    def test_future_prices_do_not_change_first_buy(self):
        data = {}
        first = dt.date(2025, 9, 1)
        for i in range(125):
            day=(first+dt.timedelta(days=i)).isoformat()
            data[day]={
                "11110": Bar(day,"11110",1000+i,1000+i,10000,1000+i),
                "99990": Bar(day,"99990",1000+3*i,1000+3*i,10000,1000+3*i),
            }
        dates=sorted(data)
        kw=dict(cutoff=dates[120],start=dates[121],initial=500000,allocation=160000,lot=100,hold_days=999)
        rule={"lookback":3,"min_return_pct":0}
        base=replay(data,rule,**kw)
        modified={d:dict(v) for d,v in data.items()}
        modified[dates[123]]["11110"]=Bar(dates[123],"11110",1,1,10000,1)
        changed=replay(modified,rule,**kw)
        a=next(x for x in base["fills"] if x["side"]=="BUY")
        b=next(x for x in changed["fills"] if x["side"]=="BUY")
        self.assertEqual((a["date"],a["code"],a["qty"],a["price"]),
                         (b["date"],b["code"],b["qty"],b["price"]))


if __name__ == "__main__":
    unittest.main()
