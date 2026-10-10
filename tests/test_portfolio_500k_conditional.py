"""50万円現物シミュレーション: 利確範囲・30営業日寄付・先読み禁止."""
import datetime as dt
import unittest
from february_walkforward import replay
from walkforward_backtest import Bar
from portfolio_500k_conditional import FROZEN_BUY, INITIAL, summary


def artificial_days(n=85):
    d=dt.date(2026,1,1)
    out=[]
    while len(out)<n:
        if d.weekday()<5:
            out.append(d.isoformat())
        d+=dt.timedelta(days=1)
    return out


def dataset():
    day=artificial_days()
    symbols={}
    for i,d in enumerate(day):
        v=100.0
        # First trade enters Feb2 at OPEN100. On Feb2 CLOSE=103,
        # after-fee positive band -> first exit Feb3 OPEN=101.
        if d=="2026-02-02":
            v=103.0
        if d=="2026-02-03":
            v=101.0
        symbols[d]={"TEST0":Bar(d,"TEST0",101.0 if d=="2026-02-03" else 100.,
                                v,10000,v, max(v,100)+1,min(v,100)-1)}
    return symbols


class CashFiveHundredThousandTests(unittest.TestCase):
    def test_eod_band_queues_following_open_not_same_day_close(self):
        data=dataset()
        r=replay(data,FROZEN_BUY,cutoff="2026-01-30",
                 start="2026-02-02",hold_days=30,max_hold_at_open=True,
                 take_profit_band=(2,5),initial=500000,allocation=100000,
                 fee_rate=.001)
        sold=[e for e in r["fills"] if e.get("side")=="SELL"]
        self.assertTrue(sold)
        self.assertEqual(sold[0]["date"],"2026-02-03")
        self.assertEqual(sold[0]["signal_reason"],"TAKE_PROFIT_BAND")
        self.assertGreater(sold[0]["realized_pnl"],0)
        self.assertTrue(all(e.get("qty",100)>0 for e in r["fills"]
                            if e.get("side") in ("BUY","SELL")))

    def test_exact_30th_held_open_even_if_later_close_explodes(self):
        data=dataset()
        first = replay(data,FROZEN_BUY,cutoff="2026-01-30",
                       start="2026-02-02",hold_days=30,max_hold_at_open=True,
                       initial=500000,allocation=100000,fee_rate=.001)
        sold=[e for e in first["fills"] if e.get("side")=="SELL"]
        self.assertTrue(sold)
        self.assertEqual(sold[0]["signal_reason"],"MAX_HOLD")
        # The first dated market session entry is Feb2; the 30th open
        # has index entry+29.
        days=sorted(data)
        expected=days[days.index("2026-02-02")+29]
        self.assertEqual(sold[0]["date"],expected)
        changed={d:dict(rows) for d,rows in data.items()}
        b=changed[expected]["TEST0"]
        changed[expected]["TEST0"]=Bar(
            expected,b.code,b.open,900.,b.volume,900.,901.,b.low)
        second=replay(changed,FROZEN_BUY,cutoff="2026-01-30",
                      start="2026-02-02",hold_days=30,max_hold_at_open=True,
                      initial=500000,allocation=100000,fee_rate=.001)
        sold2=[e for e in second["fills"] if e.get("side")=="SELL"]
        self.assertEqual(sold[0],sold2[0])

    def test_band_does_not_trigger_on_a_jump_above_upper_bound(self):
        data=dataset()
        data["2026-02-02"]["TEST0"]=Bar("2026-02-02","TEST0",
                                           100.,110.,10000,110.,111.,99.)
        r=replay(data,FROZEN_BUY,cutoff="2026-01-30",start="2026-02-02",
                 hold_days=30,max_hold_at_open=True,
                 take_profit_band=(2,5),initial=500000,
                 allocation=100000,fee_rate=.001)
        sold=[e for e in r["fills"] if e.get("side")=="SELL"]
        self.assertTrue(sold)
        self.assertEqual(sold[0]["signal_reason"],"MAX_HOLD")

    def test_invalid_band_and_no_paper_borrowing(self):
        data=dataset()
        for band in ((5,2),(2,2),(-1,5),(2,101),(float("nan"),5)):
            with self.assertRaises(ValueError):
                replay(data,FROZEN_BUY,cutoff="2026-01-30",
                       start="2026-02-02",take_profit_band=band)
        r=replay(data,FROZEN_BUY,cutoff="2026-01-30",
                 start="2026-02-02",hold_days=30,
                 max_hold_at_open=True,take_profit_band=(2,5))
        self.assertGreaterEqual(r["cash"],0)
        self.assertEqual(INITIAL,500000)
        self.assertEqual(summary(r)["ending_cash_jpy"],r["cash"])


if __name__=="__main__":
    unittest.main()
