#!/usr/bin/env python3
"""Historical chart-pattern BUY plus paired profit/stop exits.

A conservative OHLC *paper* model, never brokerage orders. An entry from a
close-of-day signal executes only at the following session's available open.
Paired exits are mutually exclusive. When both prices touch in the same bar,
STOP wins because daily OHLC cannot establish their chronological order.
"""
import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from fast_strategy_grid import BUY, buy_rule, prepare
from walkforward_backtest import load_bars
from jpx_market_risk import risk_as_of_close,risk_as_of_open

PATTERN_LOOKBACK={"dip":5,"momentum":20,"breakout":20,"reversal":20,"volume":5}
CONFIGS=tuple((stop,target,days) for stop in (3,5,8)
              for target in (6,10,15) for days in (5,10,20))

@dataclass(frozen=True)
class Bracket:
    stop_pct: float = 5
    target_pct: float = 10
    max_hold_sessions: int = 10

    def __post_init__(self):
        if not (0 < self.stop_pct < 100 and 0 < self.target_pct <= 100
                and isinstance(self.max_hold_sessions,int)
                and self.max_hold_sessions>0):
            raise ValueError("Invalid bracket: stop, target and hold must be positive")

    def prices(self, entry):
        if not math.isfinite(entry) or entry<=0:raise ValueError("Invalid entry")
        return entry*(1-self.stop_pct/100),entry*(1+self.target_pct/100)

def complete_bar(bar):
    if bar is None or bar.high is None or bar.low is None:return False
    nums=(bar.open,bar.close,bar.high,bar.low,bar.adj_close)
    return (all(math.isfinite(x) and x>0 for x in nums)
            and bar.low<=min(bar.open,bar.close)
            and bar.high>=max(bar.open,bar.close)
            and bar.volume>0)

def paired_exit(bar,entry,bracket,first_session=False):
    """(kind, executed_price). Stop-market fill at trigger is illustrative.
    Entry-session exit checks only AFTER the opening purchase.
    """
    if not complete_bar(bar):return None
    stop,target=bracket.prices(entry)
    if not first_session:
        if bar.open<=stop:return ("STOP_GAP",bar.open)
        if bar.open>=target:return ("TARGET_GAP",bar.open)
    # Worst plausible path when H and L cross both thresholds.
    if bar.low<=stop:return ("STOP",stop)
    if bar.high>=target:return ("TARGET",target)
    return None

def pattern_signals(data,days,features,index,pattern):
    if pattern not in PATTERN_LOOKBACK:raise ValueError("Unknown pattern")
    lb=PATTERN_LOOKBACK[pattern]
    if index<lb:return []
    day=days[index]
    latest=data[day]
    ranked=[]
    for code,bar in latest.items():
        if not complete_bar(bar) or risk_as_of_close(code,day):continue
        if any(code not in data[days[j]] for j in range(index-lb,index+1)):
            continue  # Sparse observations are not consecutive market sessions.
        feature=features[day].get(code)
        if not buy_rule(feature,pattern):continue
        ch,r5,r20,vr,trend=feature
        score={"dip":-r5,"momentum":r5,"breakout":r20,
               "reversal":-r20,"volume":vr}[pattern]
        if score is not None and math.isfinite(score):
            ranked.append((-score,code))
    ranked.sort()
    return [code for _,code in ranked]

def backtest(data,days,features,pattern,bracket,start,end,initial=500000,
             per_position=100000,fee=0.001,lot=100,max_positions=5):
    """Point-in-time, cash-only strategy. No liquidation after final bar."""
    if pattern not in PATTERN_LOOKBACK:raise ValueError("Unknown pattern")
    if not (math.isfinite(initial) and initial>0
            and math.isfinite(per_position) and per_position>0
            and math.isfinite(fee) and 0<=fee<1
            and isinstance(lot,int) and lot>0
            and isinstance(max_positions,int) and max_positions>0):
        raise ValueError("Invalid cash-only account")
    indexes=[i for i,d in enumerate(days) if start<=d<=end]
    if not indexes or indexes!=list(range(indexes[0],indexes[-1]+1)):
        raise ValueError("Invalid replay window")
    cash=float(initial);held={};fills=[];equity=[];unknown_sessions=0
    unknown_ohlc=0;ambiguous_bars=0
    begin,end_index=indexes[0],indexes[-1]
    pending=pattern_signals(data,days,features,begin-1,pattern) if begin else []
    max_dd=0.0;peak=initial;time_orders=set()
    for i in indexes:
        day=days[i];bars=data[day]
        for code in sorted(list(time_orders)):
            pos=held.get(code)
            if pos is None:time_orders.discard(code);continue
            b=bars.get(code)
            if b is None or not math.isfinite(b.open) or b.open<=0 or b.volume<=0:
                continue  # The liquidation request survives a missing open.
            proceeds=pos["qty"]*b.open*(1-fee);cash+=proceeds
            fills.append({"date":day,"code":code,"side":"SELL","reason":"MAX_HOLD_NEXT_OPEN",
                          "qty":pos["qty"],"price":b.open,
                          "pnl":round(proceeds-pos["cost"],2)})
            del held[code];time_orders.discard(code)
        for code in pending:
            if code in held or len(held)>=max_positions or risk_as_of_open(code,day):continue
            b=bars.get(code)
            if not complete_bar(b):continue
            budget=min(cash,per_position)
            qty=int(budget/(b.open*(1+fee))//lot)*lot
            if qty<lot:continue
            spent=qty*b.open*(1+fee)
            if spent>cash+1e-7:raise AssertionError("Insufficient cash")
            cash-=spent
            held[code]={"qty":qty,"entry":b.open,"cost":spent,"index":i}
            fills.append({"date":day,"code":code,"side":"BUY","qty":qty,
                          "price":b.open,"paired_stop":bracket.prices(b.open)[0],
                          "paired_target":bracket.prices(b.open)[1]})
        pending=[]
        for code,pos in list(held.items()):
            b=bars.get(code)
            if not complete_bar(b):
                unknown_ohlc+=1
                continue
            stop,target=bracket.prices(pos["entry"])
            if b.low<=stop and b.high>=target:
                ambiguous_bars+=1
            outcome=paired_exit(b,pos["entry"],bracket,first_session=i==pos["index"])
            if outcome is None:
                if (risk_as_of_close(code,day) or
                        i-pos["index"]>=bracket.max_hold_sessions-1):
                    time_orders.add(code)  # Executes NEXT open; no lookahead.
                continue
            why,px=outcome
            proceeds=pos["qty"]*px*(1-fee)
            cash+=proceeds
            fills.append({"date":day,"code":code,"side":"SELL","reason":why,
                          "qty":pos["qty"],"price":px,
                          "pnl":round(proceeds-pos["cost"],2)})
            del held[code];time_orders.discard(code)
        if cash < -1e-6 or len(held)>max_positions:
            raise AssertionError("Cash-only long account invariant failed")
        if all(code in bars and math.isfinite(bars[code].close) and bars[code].close>0 for code in held):
            net=cash+sum(pos["qty"]*bars[code].close for code,pos in held.items())
        else:
            net=None;unknown_sessions+=1
        equity.append((day,round(net,2) if net is not None else None))
        if net is not None and not unknown_sessions:
            peak=max(peak,net)
            max_dd=max(max_dd,(peak-net)/peak*100)
        # All new entry decisions happen AFTER the current close.
        if i<end_index:
            pending=pattern_signals(data,days,features,i,pattern)
            pending=[x for x in pending if x not in held]
    final=equity[-1][1]
    complete=(final is not None and not unknown_sessions and not unknown_ohlc)
    sells=[x for x in fills if x["side"]=="SELL"]
    return {"buy_pattern":pattern,"bracket":{"stop_pct":bracket.stop_pct,
             "target_pct":bracket.target_pct,"max_hold_sessions":bracket.max_hold_sessions},
            "first_date":days[begin],"last_date":days[end_index],
            "ending_cash":round(cash,2),"ending_equity":final,
            "net_pnl":round(final-initial,2) if complete else None,
            "max_drawdown_pct":round(max_dd,3) if not unknown_sessions else None,
            "closed_trades":len(sells),
            "wins":sum(x["pnl"]>0 for x in sells),
            "losses":sum(x["pnl"]<=0 for x in sells),
            "closed_realized_pnl":round(sum(x["pnl"] for x in sells),2),
            "remaining_positions":len(held),"missing_equity_sessions":unknown_sessions,
            "missing_intraday_exposure_sessions":unknown_ohlc,
            "both_barriers_hit_stop_first":ambiguous_bars,
            "priced_complete":complete,"fills":fills,
            "validation_status":"PROVISIONAL_UNVERIFIED",
            "warnings":["Stop market fills and profit limits are hypothetical; gaps, queues and slippage can worsen actual execution.",
                        "Corporate actions, delistings, dividends and tick-size/price-limit rules are not yet fully reconciled."]}

def compare(data,train_to="2026-01-30",test_from="2026-02-02",
            initial=500000,min_closed=3):
    days,features=prepare(data)
    prior=[d for d in days if d<=train_to]
    if len(prior)<100 or test_from<=train_to or test_from not in days:
        raise ValueError("Missing chronological training/holdout window")
    split_idx=int(len(prior)*.7)
    left=(prior[0],prior[split_idx-1])
    right=(prior[split_idx],prior[-1])
    ranked=[]
    for pattern in BUY:
        for stop,target,hold in CONFIGS:
            bracket=Bracket(stop,target,hold)
            a=backtest(data,days,features,pattern,bracket,*left,initial=initial)
            b=backtest(data,days,features,pattern,bracket,*right,initial=initial)
            if (not a["priced_complete"] or not b["priced_complete"]
                or min(a["closed_trades"],b["closed_trades"])<min_closed):
                continue
            score=min(a["net_pnl"],b["net_pnl"])
            ranked.append((score,pattern,stop,target,hold,a,b))
    ranked.sort(key=lambda r:(-r[0],r[1],r[2],r[3],r[4]))
    winner=next((r for r in ranked if r[0]>0),None)
    holdout=(backtest(data,days,features,winner[1],Bracket(*winner[2:5]),
                      test_from,days[-1],initial=initial) if winner else None)
    return {"evaluation":"BUY_PATTERN_PLUS_PAIRED_STOP_AND_TARGET",
            "params_tested":len(BUY)*len(CONFIGS),
            "training_eligible":len(ranked),
            "selected_pre_test":{"pattern":winner[1],"stop_pct":winner[2],
                "target_pct":winner[3],"max_hold_sessions":winner[4],
                "worst_train_pnl_yen":round(winner[0],2)} if winner else None,
            "training_top5":[{"pattern":r[1],"stop_pct":r[2],"target_pct":r[3],
                "max_hold_sessions":r[4],"worst_train_pnl_yen":round(r[0],2)}
                for r in ranked[:5]],
            "holdout":holdout,"holdout_start":test_from,"train_end":train_to,
            "validation_status":"PROVISIONAL_UNVERIFIED",
            "note":"Hypothetical next-open buys and paired exits. No live orders. No verified recommendation."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--from-neon",action="store_true")
    ap.add_argument("--root",default="archive/daily")
    ap.add_argument("--out",default="private-bracket-grid.json")
    ap.add_argument("--train-to",default="2026-01-30")
    ap.add_argument("--test-from",default="2026-02-02")
    a=ap.parse_args()
    if a.from_neon:
        from february_walkforward import load_private_neon
        data=load_private_neon()
    else:data=load_bars(a.root)
    result=compare(data,train_to=a.train_to,test_from=a.test_from)
    with open(a.out,"w",encoding="utf8") as fh:
        json.dump(result,fh,ensure_ascii=False,indent=2)
    # Private price records and individual fills never enter public logs.
    print(json.dumps({"evaluation":result["evaluation"],"params_tested":result["params_tested"],
        "training_eligible":result["training_eligible"],
        "selected":result["selected_pre_test"],
        "holdout_complete":result["holdout"]["priced_complete"] if result["holdout"] else None,
        "status":result["validation_status"]},ensure_ascii=False))

if __name__=="__main__":
    main()
