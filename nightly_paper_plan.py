#!/usr/bin/env python3
"""One evening paper-order proposal only. No brokerage API or real orders.

Account JSON: {"cash": 500000, "holdings": {"72030": {"qty": 100, "entry_price": 1000}}}
Both sides are next-session *candidates*, not executable orders.
"""
import argparse
import datetime as dt
import json
from chart_bracket import Bracket
from pathlib import Path
from walkforward_backtest import load_bars, rule_matches

def build_plan(data,account,rule,as_of=None,max_age_days=7,max_buy_candidates=5,lot_size=100,fee_pct=0,stop_pct=5,target_pct=10):
    if not data: raise ValueError("No data")
    if not (0 <= fee_pct < 1 and lot_size >= 1 and max_buy_candidates >= 0):
        raise ValueError("Invalid settings")
    bracket=Bracket(stop_pct,target_pct)
    last=max(data)
    now=dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    days_old=(now-dt.date.fromisoformat(last)).days
    holdings=account.get("holdings",{})
    cash=float(account.get("cash",0))
    if cash < 0 or any(int(p["qty"]) <= 0 for p in holdings.values()):
        raise ValueError("Margin or short positions are not supported")
    result={"as_of":now.isoformat(),"last_observed_session":last,"data_age_days":days_old,
            "initial_cash":cash,"stale":days_old>max_age_days or days_old<0,
            "orders":[],"held_exit_templates":[],"warnings":[],"mode":"PAPER_PREVIEW_ONLY",
            "allowed":["BUY_CASH","SELL_HELD"],"forbidden":["SHORT","FUTURES","MARGIN","REAL_ORDER"]}
    if result["stale"]:
        result["warnings"].append("Last available close is stale or in the future: NO live-order candidates.")
        return result
    # One paired exit describes only shares already in the supplied holdings.
    # It is NOT two independent full-quantity stock sell orders.
    for code,pos in sorted(holdings.items()):
        entry=float(pos.get("entry_price",0))
        if entry<=0:continue
        stop,target=bracket.prices(entry)
        result["held_exit_templates"].append({
            "code":code,"qty":int(pos["qty"]),
            "reference_paid_price":entry,
            "stop_trigger_reference":round(stop,4),
            "take_profit_limit_reference":round(target,4),
            "kind":"OCO_PAIRED_SELL_PREVIEW_ONLY",
            "not_executed":True,
            "note":"Requires broker support and available owned shares; prices/ticks may need adjustment."})
    # Only open share balances supplied by the user can ever be proposed for sale.
    hold_days=int(rule.get("max_hold_calendar_days",0))
    for code,pos in sorted(holdings.items()):
        held=int(pos["qty"])
        if hold_days and "purchased_on" in pos:
            aged=(now-dt.date.fromisoformat(pos["purchased_on"])).days
            if aged>=hold_days and code in data[last]:
                result["orders"].append({"side":"SELL_HELD","code":code,"qty":held,
                                         "reference_close":data[last][code].close,
                                         "reason":"holding_period","not_executed":True})
    history={}
    for day in sorted(data):
        for code,bar in data[day].items():
            history.setdefault(code,[]).append(bar)
    budget_left=cash
    buy_budget=float(rule.get("max_new_position_yen",100000))
    for code,bar in sorted(data[last].items()):
        if code in holdings or bar.volume<=0 or not rule_matches(history[code],rule):
            continue
        if len([o for o in result["orders"] if o["side"]=="BUY_CASH"])>=max_buy_candidates:break
        allocation=min(budget_left,buy_budget)
        quantity=int(allocation/(bar.close*(1+fee_pct))//lot_size)*lot_size
        if quantity<lot_size:continue
        reserved=quantity*bar.close*(1+fee_pct)
        budget_left-=reserved
        stop,target=bracket.prices(bar.close)
        result["orders"].append({"side":"BUY_CASH","code":code,"qty":quantity,
                                 "reference_close":bar.close,"estimated_cost":round(reserved,2),
                                 "reason":"screening_rule","not_executed":True,
                                 "paired_sell_after_buy":{
                                     "kind":"IFD_OCO_ILLUSTRATION_ONLY",
                                     "activate":"ONLY_AFTER_CONFIRMED_BUY_FILL",
                                     "stop_trigger_reference":round(stop,4),
                                     "take_profit_limit_reference":round(target,4),
                                     "qty_if_filled":quantity,
                                     "reference_entry_is_not_actual_fill":True}})
    result["warnings"].append("Next-session opening prices may differ; recheck cash, order size and tradability before any real manual order.")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="archive/daily")
    p.add_argument("--account",required=True,help="Private account state JSON; never commit")
    p.add_argument("--rule-json",default='{"lookback":5,"min_return_pct":2,"min_volume":100000,"max_new_position_yen":100000}')
    p.add_argument("--as-of",help="YYYY-MM-DD; omitted means local execution date")
    p.add_argument("--out",default="nightly-paper-plan.json")
    a=p.parse_args()
    result=build_plan(load_bars(a.root),json.loads(Path(a.account).read_text()),json.loads(a.rule_json),a.as_of)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"as_of":result["as_of"],"stale":result["stale"],
                      "candidates":len(result["orders"]),"out":a.out},ensure_ascii=False))
if __name__=="__main__": main()
