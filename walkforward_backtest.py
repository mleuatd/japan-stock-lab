#!/usr/bin/env python3
"""Point-in-time daily bar paper backtest. Standard library; no live orders.
Input: private CSV.gz archives (Date,Code,O,H,L,C,Vo,Va,AdjC,AdjFactor).
Only historical bars, no internet access. Orders generated at close fill at NEXT session OPEN.
"""
import argparse
import csv
import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Bar:
    date: str
    code: str
    open: float
    close: float
    volume: int
    adj_close: float
    high: float | None = None
    low: float | None = None

def load_bars(root):
    bydate=defaultdict(dict)
    for path in sorted(Path(root).rglob("*.csv.gz")):
        with gzip.open(path,"rt",encoding="utf-8",newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    b=Bar(r["Date"],r["Code"],float(r["O"]),float(r["C"]),
                          int(float(r["Vo"])),float(r["AdjC"]),
                          float(r["H"]) if r.get("H") else None,
                          float(r["L"]) if r.get("L") else None)
                except (ValueError,TypeError):
                    continue
                if (b.date!=path.name[:10] or not all(math.isfinite(value) and value>0 for value in (b.open,b.close,b.adj_close)) or b.volume<0 or (b.high is not None and not math.isfinite(b.high))
                        or (b.low is not None and not math.isfinite(b.low))
                        or (b.high is not None and b.high < max(b.open,b.close))
                        or (b.low is not None and b.low > min(b.open,b.close))):
                    continue
                bydate[b.date][b.code]=b
    return dict(sorted(bydate.items()))

def rule_matches(history, rule):
    """Everything visible here ends at today's close; no next-day bar passed in."""
    lookback=int(rule.get("lookback",5))
    threshold=float(rule.get("min_return_pct",0))
    min_volume=int(rule.get("min_volume",0))
    if lookback<1 or len(history)<lookback+1:
        return False
    today=history[-1]
    pct=(today.adj_close/history[-1-lookback].adj_close-1)*100
    return pct>=threshold and today.volume>=min_volume

def simulate(data,rule,initial_cash=500_000,allocation=0.1,fee_pct=0.0,hold_days=5,lot_size=100):
    """Return replay event log. Orders never fill on signal day. Conservatively
    skip unavailable next-open prices; no intra-day execution claims."""
    if not(initial_cash>0 and 0<allocation<=1 and 0<=fee_pct<1 and hold_days>=1 and lot_size>=1):
        raise ValueError("invalid allocation, fees, holding duration or lot size")
    dates=sorted(data)
    history=defaultdict(list)
    cash=float(initial_cash)
    positions={}
    orders=[]
    events=[]
    equity=[]
    for index,date in enumerate(dates):
        current=data[date]
        # Sell requests survive a missing or suspended opening session.
        # Buy requests expire rather than executing on a later, unintended day.
        retry_sells=[]
        # Existing holdings are sold first to free cash, then long-only buys are evaluated.
        for o in sorted(orders,key=lambda item: 0 if item["side"]=="SELL" else 1):
            if o["side"] not in ("BUY","SELL"):
                raise ValueError("Only cash BUY and held-stock SELL are allowed")
            b=current.get(o["code"])
            if not b or not math.isfinite(b.open) or b.open<=0 or b.volume<=0:
                events.append(dict(date=date,code=o["code"],side=o["side"],action="SKIP_NO_OPEN"))
                if o["side"]=="SELL" and o["code"] in positions:
                    retry_sells.append(o)
                continue
            code=o["code"]
            if o["side"]=="BUY":
                if code in positions: continue
                # Size from money available AT execution time; never assume unlimited liquidity.
                budget=min(cash,initial_cash*allocation)
                qty=int(budget/(b.open*(1+fee_pct))//lot_size)*lot_size
                if qty<lot_size:
                    events.append(dict(date=date,code=code,side="BUY",action="SKIP_CASH"))
                    continue
                cost=qty*b.open*(1+fee_pct)
                cash-=cost
                positions[code]={"qty":qty,"entry":b.open,"date":date,"index":index,"cost":cost}
                events.append(dict(date=date,code=code,side="BUY",action="FILLED",qty=qty,price=b.open,cash=round(cash,2)))
            else:
                if code not in positions: continue
                pos=positions.pop(code)
                received=pos["qty"]*b.open*(1-fee_pct)
                cash+=received
                events.append(dict(date=date,code=code,side="SELL",action="FILLED",qty=pos["qty"],price=b.open,pnl=round(received-pos["cost"],2),cash=round(cash,2)))
        orders=retry_sells
        # All current-day prices become known only after today's CLOSE.
        for code,b in current.items():
            history[code].append(b)
        # Exit scheduling and fresh buy signals are decisions at today's CLOSE.
        exits={o["code"] for o in retry_sells}
        for code,pos in positions.items():
            if code in exits:
                continue
            if index-pos["index"]>=hold_days-1:
                orders.append({"side":"SELL","code":code})
                exits.add(code)
        for code,b in sorted(current.items()):
            if code not in positions and code not in exits and rule_matches(history[code],rule):
                orders.append({"side":"BUY","code":code})
        # Mark to market only using observable latest CLOSE, not future close.
        mtm=sum(pos["qty"]*current[code].close for code,pos in positions.items()
                if code in current and math.isfinite(current[code].close) and current[code].close>0)
        missing=sum(1 for code in positions if code not in current
                    or not math.isfinite(current[code].close) or current[code].close<=0)
        equity.append(dict(date=date,cash=round(cash,2),equity=round(cash+mtm,2) if not missing else None,open_positions=len(positions)))
    # Do not fabricate liquidation after dataset ends; outstanding orders are unfilled.
    realized=sum(e.get("pnl",0) for e in events)
    fills=[e for e in events if e["action"]=="FILLED"]
    if any(pos["qty"]<=0 for pos in positions.values()) or cash < -0.00001:
        raise AssertionError("Long-only, cash-funded invariant violated")
    return {"initial_cash":initial_cash,"ending_cash":round(cash,2),
            "realized_pnl":round(realized,2),"fills":fills,"events":events,
            "equity_curve":equity,"unfilled_last_day_orders":orders,
            "open_positions":positions,
            "note":"Last-day positions are open. Equity is null if a held security has no closing price."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="archive/daily")
    p.add_argument("--rule-json",default='{"lookback":5,"min_return_pct":2,"min_volume":100000}')
    p.add_argument("--initial-cash",type=float,default=500_000)
    p.add_argument("--allocation",type=float,default=.1)
    p.add_argument("--hold-days",type=int,default=5)
    p.add_argument("--fee-pct",type=float,default=0)
    p.add_argument("--lot-size",type=int,default=100)
    p.add_argument("--out",default="backtest-results.json")
    a=p.parse_args()
    data=load_bars(a.root)
    if not data: raise SystemExit("No valid private day bars found")
    result=simulate(data,json.loads(a.rule_json),a.initial_cash,a.allocation,a.fee_pct,a.hold_days,a.lot_size)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"sessions":len(data),"fills":len(result["fills"]),
                       "realized_pnl":result["realized_pnl"],"open_positions":len(result["open_positions"]),
                       "result_path":a.out}))
if __name__=="__main__": main()
