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
    next_session={day:dates[j+1] for j,day in enumerate(dates[:-1])}
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
                if (bars[i+2].date>cutoff or bars[i+1].open<=0 or
                    bars[i+1].date != next_session.get(d) or
                    bars[i+2].date != next_session.get(bars[i+1].date)):
                    continue
                # Equivalent to rule_matches(bars[:i+1], rule) without
                # allocating an ever-growing prefix for every candidate.
                previous=bars[i-rule["lookback"]].adj_close
                current=bars[i]
                if (previous>0 and
                    (current.adj_close/previous-1)*100 >= rule["min_return_pct"] and
                    current.volume>=rule["min_volume"]):
                    r=(bars[i+2].open/bars[i+1].open-1)*100
                    by_segment[0 if d<=dates[split-1] else 1].append(r)
        a,b=by_segment
        if len(a)<min_events or len(b)<max(8,min_events//3):continue
        # Require positive net-ish edge in both segments, conservative preference.
        score=min(mean(a),mean(b))
        possibilities.append((score,rule,len(a),len(b),mean(a),mean(b)))
    possibilities.sort(key=lambda p:p[0],reverse=True)
    return possibilities

def replay(data,rule,cutoff=CUTOFF,start=START,initial=500000,lot=100,allocation=100000,hold_days=5,fee_rate=.001,corporate_actions=None,slippage_rate=0.0,tax_rate=0.0):
    """Long-only historical paper account. Corporate events must be supplied explicitly.

    corporate_actions: {date: {code: {"split_ratio": positive number,
                     "cash_dividend_per_share": nonnegative number}}}.
    The split event is applied before OPEN orders on the effective date.
    Dividend cash is credited on the supplied *payment* date, not ex-date.
    Missing events are not inferred from adjustment factors. Report is provisional.
    """
    if not (initial > 0 and lot > 0 and allocation > 0 and hold_days > 0
            and 0 <= fee_rate < 1 and 0 <= slippage_rate < 1 and 0 <= tax_rate < 1):
        raise ValueError("Invalid long-only paper-account parameters")
    corporate_actions=corporate_actions or {}
    dates=sorted(data)
    if cutoff not in dates: raise ValueError("Cutoff trading session missing")
    if start<=cutoff: raise ValueError("Replay must start after training cutoff")
    if start not in dates or dates[dates.index(cutoff)+1] != start:
        raise ValueError("Start must equal the first market session after cutoff")
    unknown_days=set(corporate_actions)-set(dates)
    if unknown_days: raise ValueError("Corporate actions must map to market sessions")
    hist=defaultdict(list)
    cash=float(initial);positions={};queue=[];ledger=[];daily=[]
    realized_pnl=0.0
    known_dividends=0.0
    for n,day in enumerate(dates):
        bars=data[day]
        # Apply only sourced and explicitly supplied corporate actions.
        for code,event in corporate_actions.get(day,{}).items():
            if code not in positions:
                continue
            pos=positions[code]
            if "split_ratio" in event:
                ratio=event["split_ratio"]
                if not (isinstance(ratio,(int,float)) and 0 < ratio < float("inf")):
                    raise ValueError("Invalid split ratio")
                new_qty=pos["qty"]*ratio
                if abs(new_qty-round(new_qty))>1e-8:
                    raise ValueError("Fractional share cash-out requires an explicit event")
                pos["qty"]=int(round(new_qty))
                ledger.append({"date":day,"code":code,"side":"ACTION","status":"SPLIT","ratio":ratio,"qty":pos["qty"]})
            if "cash_dividend_per_share" in event:
                amount=event["cash_dividend_per_share"]
                if not (isinstance(amount,(int,float)) and 0 <= amount < float("inf")):
                    raise ValueError("Invalid dividend")
                gross=pos["qty"]*amount
                net=gross*(1-tax_rate)
                cash+=net
                known_dividends+=net
                ledger.append({"date":day,"code":code,"side":"ACTION","status":"DIVIDEND","gross":round(gross,2),"net":round(net,2)})
        # At the first replay open: execute Jan30-close orders from Jan30 signal.
        if day>cutoff and day>=start:
            for order in sorted(queue,key=lambda o:0 if o["side"]=="SELL" else 1):
                code=order["code"];b=bars.get(code)
                if not b or b.open<=0 or b.volume<=0:
                    ledger.append({"date":day,"code":code,"side":order["side"],"status":"NO_OPEN"});continue
                if order["side"]=="SELL":
                    if code not in positions:continue
                    pos=positions[code]
                    execution_price=b.open*(1-slippage_rate)
                    proceeds=pos["qty"]*execution_price*(1-fee_rate)
                    gross_gain=proceeds-pos["cost"]
                    tax=max(0,gross_gain)*tax_rate
                    received=proceeds-tax
                    cash+=received
                    realized_pnl+=received-pos["cost"]
                    del positions[code]
                    ledger.append({"date":day,"code":code,"side":"SELL","qty":pos["qty"],"price":round(execution_price,4),
                                   "tax":round(tax,2),"realized_pnl":round(received-pos["cost"],2)})
                else:
                    if code in positions:continue
                    limit=min(cash,allocation)
                    execution_price=b.open*(1+slippage_rate)
                    qty=int(limit/(execution_price*(1+fee_rate))//lot)*lot
                    if qty<lot:continue
                    spent=qty*execution_price*(1+fee_rate)
                    if spent > cash+1e-8: raise AssertionError("Insufficient cash")
                    cash-=spent
                    positions[code]={"qty":qty,"cost":spent,"index":n}
                    ledger.append({"date":day,"code":code,"side":"BUY","qty":qty,"price":round(execution_price,4)})
        queue=[]
        for code,b in bars.items():hist[code].append(b)
        if day<cutoff:continue
        # Decisions at CLOSE, after that session has become observable.
        exiting=set()
        for code,pos in positions.items():
            if n-pos["index"] >= hold_days-1:
                queue.append({"side":"SELL","code":code});exiting.add(code)
        # Prioritize the strongest observable signal, not alphabetic ticker order.
        # Never inspect next-session prices while ranking today's candidates.
        lookback=int(rule.get("lookback",5))
        ranked=[]
        for code,b in bars.items():
            if code in positions or code in exiting or b.volume<=0:
                continue
            history=hist[code]
            if not rule_matches(history,rule):
                continue
            strength=(history[-1].adj_close/history[-1-lookback].adj_close-1)*100
            ranked.append((-strength,code))
        ranked.sort()  # stable tie-break by code
        candidates=[code for _,code in ranked]
        for code in candidates[:10]:
            queue.append({"side":"BUY","code":code})
        if day>=start:
            if cash < -0.0001 or any(x["qty"]<=0 for x in positions.values()):
                raise AssertionError("Non-cash or short position")
            if all(code in bars and bars[code].close > 0 for code in positions):
                value=cash+sum(pos["qty"]*bars[code].close for code,pos in positions.items())
            else:value=None
            daily.append({"date":day,"cash":round(cash,2),"total_equity":round(value,2) if value is not None else None,
                          "holdings":len(positions)})
    known_values=[day["total_equity"] for day in daily]
    if all(v is not None for v in known_values):
        high=initial
        max_dd=0.0
        for value in known_values:
            high=max(high,value)
            max_dd=max(max_dd,(high-value)/high*100)
    else:
        max_dd=None
    return {"cash":round(cash,2),"held":positions,"fills":ledger,"equity":daily,
            "final_equity":known_values[-1] if known_values else None,
            "realized_pnl":round(realized_pnl,2),
            "known_net_dividends":round(known_dividends,2),
            "max_drawdown_pct":round(max_dd,4) if max_dd is not None else None,
            "unfilled_after_final_session":queue,
            "validation_status":"PROVISIONAL_UNVERIFIED",
            "accounting_note":"Corporate actions require complete dated external events; no automatic inference."}

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
