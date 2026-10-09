#!/usr/bin/env python3
"""Frozen-as-of walk-forward experiment, long-only cash and next-session fills.
No actual brokerage orders. Uses private Neon when DATABASE_URL provided.
"""
import argparse, csv, json, os
from collections import defaultdict
from statistics import mean
from walkforward_backtest import Bar,load_bars,rule_matches

CUTOFF="2026-01-30"
START="2026-02-02"
def load_private_neon():
    import psycopg
    u=os.environ.get("DATABASE_URL")
    if not u: raise RuntimeError("DATABASE_URL missing")
    data=defaultdict(dict)
    with psycopg.connect(u,sslmode="require") as con:
        with con.cursor(name="chronological_backtest") as cur:
            cur.execute("""SELECT trading_date,security_code,open_price,close_price,volume,adjusted_close
            FROM daily_bar ORDER BY trading_date,security_code""")
            for date,code,o,c,v,a in cur:
                if None in (o,c,v,a) or min(o,c,a)<=0:continue
                day=date.isoformat()
                data[day][code]=Bar(day,code,float(o),float(c),int(v),float(a))
    return dict(sorted(data.items()))

def candidate_rules():
    return [{"lookback":lb,"min_return_pct":pct,"min_volume":vol}
            for lb in (3,5,10,20) for pct in (-10,-5,0,3,8)
            for vol in (0,100000)]

def frozen_train(data,cutoff,min_events=25):
    dates=[d for d in sorted(data) if d<=cutoff]
    if len(dates)<120: raise ValueError("Insufficient pre-cutoff history")
    # All model tuning is strictly prior to cutoff.
    split=int(len(dates)*.7)
    features=defaultdict(list)
    for day in dates:
        for code,b in data[day].items(): features[code].append(b)
    possibilities=[]
    for rule in candidate_rules():
        by_segment=[[],[]]
        for bars in features.values():
            for i in range(rule["lookback"],len(bars)-2):
                d=bars[i].date
                if d>cutoff:break
                # Observe close on d; buy next OPEN; sell subsequent OPEN.
                # Both future prices must also be <= cutoff for training.
                if bars[i+2].date>cutoff or bars[i+1].open<=0:continue
                if rule_matches(bars[:i+1],rule):
                    r=(bars[i+2].open/bars[i+1].open-1)*100
                    by_segment[0 if d<=dates[split-1] else 1].append(r)
        a,b=by_segment
        if len(a)<min_events or len(b)<max(8,min_events//3):continue
        # Require positive net-ish edge in both segments, conservative preference.
        score=min(mean(a),mean(b))
        possibilities.append((score,rule,len(a),len(b),mean(a),mean(b)))
    possibilities.sort(key=lambda p:p[0],reverse=True)
    return possibilities

def replay(data,rule,cutoff=CUTOFF,start=START,initial=500000,lot=100,allocation=100000,hold_days=5,fee_rate=.001):
    dates=sorted(data)
    if cutoff not in dates: raise ValueError("Cutoff trading session missing")
    if start<=cutoff: raise ValueError("Replay must start after training cutoff")
    hist=defaultdict(list)
    cash=float(initial);positions={};queue=[];ledger=[];daily=[]
    for n,day in enumerate(dates):
        bars=data[day]
        # At the first replay open: execute Jan30-close orders from Jan30 signal.
        if day>cutoff and day>=start:
            for order in sorted(queue,key=lambda o:0 if o["side"]=="SELL" else 1):
                code=order["code"];b=bars.get(code)
                if not b or b.open<=0 or b.volume<=0:
                    ledger.append({"date":day,"code":code,"side":order["side"],"status":"NO_OPEN"});continue
                if order["side"]=="SELL":
                    if code not in positions:continue
                    pos=positions.pop(code);received=pos["qty"]*b.open*(1-fee_rate)
                    cash+=received
                    ledger.append({"date":day,"code":code,"side":"SELL","qty":pos["qty"],"price":b.open,
                                   "realized_pnl":round(received-pos["cost"],2)})
                else:
                    if code in positions:continue
                    limit=min(cash,allocation)
                    qty=int(limit/(b.open*(1+fee_rate))//lot)*lot
                    if qty<lot:continue
                    spent=qty*b.open*(1+fee_rate);cash-=spent
                    positions[code]={"qty":qty,"cost":spent,"index":n}
                    ledger.append({"date":day,"code":code,"side":"BUY","qty":qty,"price":b.open})
        queue=[]
        for code,b in bars.items():hist[code].append(b)
        if day<cutoff:continue
        # Decisions at CLOSE, after that session has become observable.
        exiting=set()
        for code,pos in positions.items():
            if n-pos["index"] >= hold_days-1:
                queue.append({"side":"SELL","code":code});exiting.add(code)
        candidates=sorted((code for code in bars if code not in positions
                           and code not in exiting and bars[code].volume>0
                           and rule_matches(hist[code],rule)),key=str)
        for code in candidates[:10]:
            queue.append({"side":"BUY","code":code})
        if day>=start:
            if cash < -0.0001 or any(x["qty"]<=0 for x in positions.values()):
                raise AssertionError("Non-cash or short position")
            if all(code in bars for code in positions):
                value=cash+sum(pos["qty"]*bars[code].close for code,pos in positions.items())
            else:value=None
            daily.append({"date":day,"cash":round(cash,2),"total_equity":round(value,2) if value is not None else None,
                          "holdings":len(positions)})
    return {"cash":round(cash,2),"held":positions,"fills":ledger,"equity":daily,
            "unfilled_after_final_session":queue}

def experiment(data,cutoff=CUTOFF,start=START):
    candidates=frozen_train(data,cutoff)
    if not candidates: return {"status":"no_qualifying_train_rule","cutoff":cutoff,"start":start,"rules_tested":len(candidate_rules())}
    score,rule,n1,n2,r1,r2=candidates[0]
    simulation=replay(data,rule,cutoff,start)
    return {"status":"completed","cutoff":cutoff,"start":start,"data_last_date":max(data),
            "rules_tested":len(candidate_rules()),
            "selected_rule_frozen_at_cutoff":rule,
            "training_only":{"split1_trades":n1,"split2_trades":n2,"mean_pct1":round(r1,3),"mean_pct2":round(r2,3)},
            "paper_result":simulation,"warnings":["Historical paper simulation, not live trading.",
            "Unadjusted open fills vs adjusted close signals need corporate action reconciliation.",
            "Corporate actions, halt/no-open, realistic liquidity, dividends/tax/slippage not yet fully modeled."]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cutoff",default=CUTOFF)
    ap.add_argument("--start",default=START)
    ap.add_argument("--root",default="archive/daily")
    ap.add_argument("--from-neon",action="store_true")
    ap.add_argument("--out",default="private-february-walkforward.json")
    a=ap.parse_args()
    data=load_private_neon() if a.from_neon else load_bars(a.root)
    result=experiment(data,a.cutoff,a.start)
    with open(a.out,"w",encoding="utf-8") as fh:json.dump(result,fh,ensure_ascii=False,indent=2)
    print(json.dumps({"status":result["status"],"cutoff":a.cutoff,"start":a.start,
        "rule_count":result["rules_tested"],"selected_rule":result.get("selected_rule_frozen_at_cutoff"),
        "paper_fills":len(result.get("paper_result",{}).get("fills",[])),
        "result_file":a.out},ensure_ascii=False))
if __name__=="__main__":main()
