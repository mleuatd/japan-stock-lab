#!/usr/bin/env python3
"""Fast nightly long-only buy/sell strategy grid. Standard library only.
Load prices ONCE; calculate indicators ONCE; replay decisions nightly, next open.
No live orders. Training rules selected before holdout, never after.
"""
import argparse, json, math
from collections import defaultdict
from walkforward_backtest import load_bars
from february_walkforward import load_private_neon

def prepare(data):
    days=sorted(data)
    histories=defaultdict(list)
    features={}
    for day in days:
        daily={}
        for code,b in data[day].items():
            h=histories[code]
            if h:
                previous=h[-1].adj_close
                change=(b.adj_close/previous-1)*100 if previous>0 else None
            else: change=None
            ret5=(b.adj_close/h[-5].adj_close-1)*100 if len(h)>=5 and h[-5].adj_close>0 else None
            ret20=(b.adj_close/h[-20].adj_close-1)*100 if len(h)>=20 and h[-20].adj_close>0 else None
            avgv=sum(x.volume for x in h[-5:])/min(5,len(h)) if h else 0
            vr=b.volume/avgv if avgv>0 and len(h)>=5 else None
            sma5=sum(x.adj_close for x in (h[-4:]+[b]))/min(5,len(h)+1)
            sma20=sum(x.adj_close for x in (h[-19:]+[b]))/min(20,len(h)+1)
            daily[code]=(change,ret5,ret20,vr,sma5>sma20 if len(h)>=19 else None)
            h.append(b)
        features[day]=daily
    return days,features

def buy_rule(f,kind):
    if not f:return False
    change,r5,r20,vr,trend=f
    if kind=="dip":return r5 is not None and -12<=r5<=-3 and change is not None and change>0
    if kind=="momentum":return r5 is not None and r5>=3 and trend is True
    if kind=="breakout":return r20 is not None and r20>8 and vr is not None and vr>=1.5
    if kind=="reversal":return r20 is not None and r20<=-8 and change is not None and change>=2
    if kind=="volume":return change is not None and change>0 and vr is not None and vr>=2
    return False

def sell_rule(f,pos,day_index,kind):
    change,r5,r20,vr,trend=f or (None,None,None,None,None)
    if kind=="flip":return change is not None and change<0
    if kind=="trend":return trend is False
    if kind=="one_day":return day_index-pos["entry_index"]>=1
    if kind=="three_day":return day_index-pos["entry_index"]>=3
    if kind=="five_day":return day_index-pos["entry_index"]>=5
    return False

def replay(data,days,features,buy,sell,from_date,to_date,initial=500000,per_position=100000,fee=0.001,lot=100):
    """Pre-signal last session allowed only to produce order for first replay open.
    Accumulate signals at CLOSE; all fills at next day's OPEN, sells before buys.
    """
    if not(0<initial and per_position>0 and 0<=fee<1 and lot>0):raise ValueError("invalid cash-only configuration")
    start=next((i for i,d in enumerate(days) if d>=from_date),len(days))
    stop=next((i for i,d in enumerate(days) if d>to_date),len(days))
    if start==len(days) or start>=stop:raise ValueError("empty test window")
    cash=float(initial);positions={};queue=[];trades=[];equity=[]
    if start>0:
        pd=days[start-1]
        queue=[("BUY",code) for code in sorted(data[pd]) if buy_rule(features[pd].get(code),buy)]
    for i in range(start,stop):
        date=days[i];bars=data[date]
        for side,code in sorted(queue,key=lambda v:0 if v[0]=="SELL" else 1):
            b=bars.get(code)
            if b is None or b.open<=0 or b.volume<=0:continue
            if side=="SELL":
                p=positions.pop(code,None)
                if p:
                    proceeds=p["qty"]*b.open*(1-fee);cash+=proceeds
                    trades.append({"date":date,"side":"SELL","code":code,"qty":p["qty"],"price":b.open,"pnl":proceeds-p["cost"]})
            else:
                if code in positions:continue
                budget=min(cash,per_position)
                qty=int(budget/(b.open*(1+fee))//lot)*lot
                if qty<lot:continue
                cost=qty*b.open*(1+fee)
                cash-=cost;positions[code]={"qty":qty,"cost":cost,"entry_index":i}
                trades.append({"date":date,"side":"BUY","code":code,"qty":qty,"price":b.open})
        if cash < -0.001:raise AssertionError("Borrowing is forbidden")
        # All decisions for next open are made exactly once at close.
        queue=[("SELL",code) for code,p in positions.items()
               if sell_rule(features[date].get(code),p,i,sell)]
        selling={code for side,code in queue}
        queue += [("BUY",code) for code in sorted(bars)
                  if code not in positions and code not in selling and buy_rule(features[date].get(code),buy)]
        # Use most recently observable close for marking held stock; missing price => unknown.
        eq=cash+sum(p["qty"]*bars[code].close for code,p in positions.items() if code in bars)
        if any(code not in bars for code in positions):eq=None
        equity.append((date,eq))
    final=equity[-1][1]
    curve=[x for _,x in equity if x is not None]
    peak=initial;drawdown=0
    for v in curve:
        peak=max(peak,v);drawdown=max(drawdown,(peak-v)/peak*100)
    return {"buy":buy,"sell":sell,"first_date":days[start],"last_date":days[stop-1],
            "ending_equity":round(final,2) if final is not None else None,
            "net_pnl":round(final-initial,2) if final is not None else None,
            "max_drawdown_pct":round(drawdown,3),"fills":len(trades),"closed_trades":sum(t["side"]=="SELL" for t in trades),
            "ending_cash":round(cash,2),"positions":len(positions),"unfilled_orders":len(queue)}

BUY=("dip","momentum","breakout","reversal","volume")
SELL=("flip","trend","one_day","three_day","five_day")

def grid(data,train_to="2026-01-30",test_from="2026-02-02"):
    days,feats=prepare(data)
    earlier=[d for d in days if d<=train_to]
    if len(earlier)<100:raise ValueError("not enough training sessions")
    split=earlier[int(len(earlier)*.7)]
    rows=[]
    for buy in BUY:
        for sell in SELL:
            a=replay(data,days,feats,buy,sell,earlier[0],earlier[earlier.index(split)-1])
            b=replay(data,days,feats,buy,sell,split,train_to)
            # Default to no trading rather than choosing a losing or untested strategy.
            if any(x["net_pnl"] is None or x["closed_trades"]<3 for x in (a,b)):continue
            rows.append({"buy":buy,"sell":sell,"train1":a,"train2":b,"score":min(a["net_pnl"],b["net_pnl"])})
    ranked=sorted(rows,key=lambda r:r["score"],reverse=True)
    winner=next((r for r in ranked if r["score"]>0),None)
    test=replay(data,days,feats,winner["buy"],winner["sell"],test_from,days[-1]) if winner else None
    return {"train_last_date":train_to,"test_first_date":test_from,"data_last_date":days[-1],
            "strategies_evaluated":len(BUY)*len(SELL),"training_eligible":len(ranked),
            "selected_pre_test":{k:winner[k] for k in ("buy","sell","score")} if winner else None,
            "held_out_result":test,"training_top5":[{"buy":r["buy"],"sell":r["sell"],"score":round(r["score"],2)} for r in ranked[:5]],
            "note":"Initial model: corporate actions, dividends, trading constraints and slippage incomplete. Not a recommendation."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--from-neon",action="store_true")
    p.add_argument("--root",default="archive/daily");p.add_argument("--out",default="private-fast-grid.json")
    args=p.parse_args()
    data=load_private_neon() if args.from_neon else load_bars(args.root)
    r=grid(data)
    with open(args.out,"w",encoding="utf8") as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps({"evaluated":r["strategies_evaluated"],"selected":r["selected_pre_test"],
                      "held_out_result":r["held_out_result"]},ensure_ascii=False))
if __name__=="__main__":main()
