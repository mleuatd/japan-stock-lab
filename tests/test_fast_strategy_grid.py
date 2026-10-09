import datetime as dt
import unittest
from walkforward_backtest import Bar
from fast_strategy_grid import prepare,replay,grid,buy_rule,sell_rule,BUY,SELL

class FastGridTests(unittest.TestCase):
 def setUp(self):
  start=dt.date(2025,1,1);self.data={}
  for i in range(150):
   d=(start+dt.timedelta(days=i)).isoformat()
   price=100+(i%20)*2
   self.data[d]={"11110":Bar(d,"11110",price,price,100000,price)}
 def test_one_fill_only_at_next_open(self):
  days,features=prepare(self.data)
  r=replay(self.data,days,features,"momentum","one_day",days[30],days[50],initial=500000)
  self.assertGreaterEqual(r["ending_cash"],0)
  self.assertIsNotNone(r["ending_equity"])
 def test_features_no_future(self):
  d,f=prepare(self.data);cut=d[40];x=f[cut]["11110"]
  changed={k:dict(v) for k,v in self.data.items()}
  for day in d[41:]:
   changed[day]["11110"]=Bar(day,"11110",999,999,99999,999)
  _,g=prepare(changed)
  self.assertEqual(x,g[cut]["11110"])
 def test_25_combinations_and_long_only(self):
  self.assertEqual(len(BUY)*len(SELL),25)
  d,f=prepare(self.data)
  for buy in BUY:
   for sell in SELL:
    r=replay(self.data,d,f,buy,sell,d[30],d[50])
    self.assertGreaterEqual(r["ending_cash"],0)
 def test_sell_not_perpetual_hold(self):
  f=(0,1,1,1,True)
  self.assertTrue(sell_rule(f,{"entry_index":0},1,"one_day"))
  self.assertTrue(sell_rule((-1,1,1,1,True),{"entry_index":0},0,"flip"))
if __name__=="__main__":unittest.main()
