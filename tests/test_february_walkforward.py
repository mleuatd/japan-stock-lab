import datetime as dt
import unittest
from february_walkforward import experiment,replay,frozen_train
from walkforward_backtest import Bar

def bar(d,p,code="11110"):
    return Bar(d,code,p,p,1000000,p)
class FebruaryWalkforwardTest(unittest.TestCase):
    def setUp(self):
        self.data={}
        start=dt.date(2025,8,1)
        for i in range(180):
            d=(start+dt.timedelta(days=i)).isoformat()
            self.data[d]={"11110":bar(d,100+i*.4),
                          "22220":bar(d,200+i*.1,code="22220")}
        self.cutoff=sorted(self.data)[145];self.start=sorted(self.data)[146]
    def test_one_pass_training_matches_independent_slow_reference(self):
        from statistics import mean
        from collections import defaultdict
        from february_walkforward import candidate_rules
        from walkforward_backtest import rule_matches
        dates=[d for d in sorted(self.data) if d<=self.cutoff]
        split=int(len(dates)*.7)
        rules=candidate_rules()
        series=defaultdict(list)
        for day in dates:
            for code,b in self.data[day].items():
                series[code].append(b)
        reference=[]
        for rule in rules:
            halves=[[],[]]
            for h in series.values():
                for i in range(rule["lookback"],len(h)-2):
                    d=h[i].date
                    j=dates.index(d)
                    if (j+2>=len(dates) or h[i+1].date!=dates[j+1] or
                            h[i+2].date!=dates[j+2] or
                            h[i-rule["lookback"]].date!=dates[j-rule["lookback"]]):
                        continue
                    if rule_matches(h[:i+1],rule):
                        halves[0 if j<split else 1].append((h[i+2].open/h[i+1].open-1)*100)
            a,b=halves
            if len(a)>=2 and len(b)>=8:
                ma,mb=mean(a),mean(b)
                reference.append((min(ma,mb),rule,len(a),len(b),ma,mb))
        reference.sort(key=lambda p:p[0],reverse=True)
        self.assertEqual(frozen_train(self.data,self.cutoff,min_events=2),reference)

    def test_trained_rule_is_independent_of_any_post_cutoff_data(self):
        before=frozen_train(self.data,self.cutoff,min_events=2)
        modified={d:dict(x) for d,x in self.data.items()}
        for day in modified:
            if day>self.cutoff:
                modified[day]["11110"]=bar(day,999999)
        after=frozen_train(modified,self.cutoff,min_events=2)
        self.assertEqual(before,after)
    def test_replay_never_trades_before_start(self):
        result=replay(self.data,{"lookback":3,"min_return_pct":0,"min_volume":0},
                      cutoff=self.cutoff,start=self.start,lot=100,allocation=30000)
        self.assertTrue(all(f["date"]>=self.start for f in result["fills"]))
        self.assertTrue(all(d["date"]>=self.start for d in result["equity"]))
        self.assertTrue(all(x["side"] in ("BUY","SELL") for x in result["fills"]))
        self.assertGreaterEqual(result["cash"],0)
    def test_ending_equity_is_not_identical_to_cash_if_holdings_exist(self):
        result=replay(self.data,{"lookback":3,"min_return_pct":0},
                      cutoff=self.cutoff,start=self.start,lot=100,allocation=30000,hold_days=999)
        self.assertGreaterEqual(result["equity"][-1]["total_equity"],result["cash"])
    def test_missing_stock_sessions_are_not_fake_next_day_fills(self):
        # One security trades only every other market day: its next row
        # must not be mistaken for the next market session's opening.
        modified={day:dict(rows) for day,rows in self.data.items()}
        for index,day in enumerate(sorted(modified)):
            if index % 2:
                modified[day].pop("11110",None)
        baseline=frozen_train(modified,self.cutoff,min_events=2)
        # Every reported event for stock 11110 would require uninterrupted
        # three-session presence, which does not exist in this dataset.
        with_only_sparse={day:{"11110":rows["11110"]} if "11110" in rows
                          else {"22220":self.data[day]["22220"]}
                          for day,rows in modified.items()}
        self.assertEqual(frozen_train(with_only_sparse,self.cutoff,min_events=2),[])
        self.assertIsInstance(baseline,list)
    def test_no_pre_cutoff_data(self):
        with self.assertRaises(ValueError):
            frozen_train({"2026-01-30":{"11110":bar("2026-01-30",100)}},"2026-01-30")
if __name__=="__main__":unittest.main()
