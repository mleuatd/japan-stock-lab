import datetime as dt
import unittest
from walkforward_backtest import Bar
from fast_strategy_grid import prepare,replay,grid

def mk(d,code,open_,close,vol=50000,adjusted=None):
    return Bar(d,code,open_,close,vol,close if adjusted is None else adjusted)

class AccuracyRegressionTests(unittest.TestCase):
    def test_incremental_indicators_equal_independent_reference(self):
        start=dt.date(2025,1,1)
        data={}
        for i in range(65):
            day=(start+dt.timedelta(days=i)).isoformat()
            value=75+i*.47+(i%9)*3
            data[day]={"11110":mk(day,"11110",value-1,value,vol=30000+(i%7)*12000)}
        days,features=prepare(data)
        bars=[data[d]["11110"] for d in days]
        for i in range(len(days)):
            b=bars[i]
            prev=(b.adj_close/bars[i-1].adj_close-1)*100 if i>=1 else None
            five=(b.adj_close/bars[i-5].adj_close-1)*100 if i>=5 else None
            twenty=(b.adj_close/bars[i-20].adj_close-1)*100 if i>=20 else None
            vr=b.volume/(sum(x.volume for x in bars[i-5:i])/5) if i>=5 else None
            trend=(sum(x.adj_close for x in bars[i-4:i+1])/5 > sum(x.adj_close for x in bars[i-19:i+1])/20) if i>=19 else None
            actual=features[days[i]]["11110"]
            for x,y in zip((prev,five,twenty,vr,trend),actual):
                if x is None:self.assertIsNone(y)
                elif isinstance(x,bool):self.assertEqual(x,y)
                else:self.assertAlmostEqual(x,y,places=10)

    def test_out_of_window_future_prices_cannot_change_past_transactions(self):
        start=dt.date(2025,1,1)
        data={}
        for i in range(90):
            day=(start+dt.timedelta(days=i)).isoformat()
            price=100+3*(i%11)
            data[day]={"11110":mk(day,"11110",price,price)}
        days,features=prepare(data)
        base=replay(data,days,features,"momentum","flip",days[25],days[50])
        modified={d:dict(v) for d,v in data.items()}
        for day in days[51:]:
            modified[day]={"11110":mk(day,"11110",100000,100000)}
        newdays,newfeatures=prepare(modified)
        after=replay(modified,newdays,newfeatures,"momentum","flip",newdays[25],newdays[50])
        self.assertEqual(base,after)

    def test_cash_and_sell_only_held(self):
        start=dt.date(2025,1,1)
        data={}
        for i in range(65):
            d=(start+dt.timedelta(days=i)).isoformat()
            p=100+2*(i%12)
            data[d]={"11110":mk(d,"11110",p,p),
                     "22220":mk(d,"22220",p+2,p+2)}
        days,features=prepare(data)
        for sell in ("flip","trend","one_day","three_day","five_day"):
            res=replay(data,days,features,"momentum",sell,days[30],days[60],initial=500000,lot=100)
            self.assertGreaterEqual(res["ending_cash"],0)
            self.assertLessEqual(res["positions"],5)

if __name__=="__main__":unittest.main()
