#!/usr/bin/env python3
"""Frozen-as-of walk-forward experiment, long-only cash and next-session fills.
No actual brokerage orders. Uses private Neon when DATABASE_URL provided.
"""
import argparse, csv, json, os, math
from collections import defaultdict, deque
from statistics import mean
from walkforward_backtest import Bar,load_bars,rule_matches
from paper_ledger_accounting import reconcile
from jpx_market_risk import risk_as_of_close,risk_as_of_open

CUTOFF="2026-01-30"
START="2026-02-02"
def load_private_neon(since=None):
    # For a frozen rule reusing only the three preceding market sessions,
    # caller may explicitly bound the SQL download to Jan 2026 onward.
    if since is not None:
        from datetime import date
        date.fromisoformat(since)
    import psycopg
    u=os.environ.get("DATABASE_URL")
    if not u: raise RuntimeError("DATABASE_URL missing")
    data=defaultdict(dict)
    with psycopg.connect(u,sslmode="require") as con:
        with con.cursor(name="chronological_backtest") as cur:
            sql = """SELECT trading_date,security_code,open_price,close_price,volume,adjusted_close,high_price,low_price
            FROM daily_bar"""
            params = ()
            if since is not None:
                sql += " WHERE trading_date >= %s::date"
                params = (since,)
            sql += " ORDER BY trading_date,security_code"
            cur.execute(sql,params)
            for date,code,o,c,v,a,h,l in cur:
                if None in (o,c,v,a) or not all(math.isfinite(float(x)) for x in (o,c,v,a)) or min(o,c,a)<=0 or v<0:continue
                day=date.isoformat()
                data[day][code]=Bar(day,code,float(o),float(c),int(v),float(a),
                    float(h) if h is not None else None,
                    float(l) if l is not None else None)
    return dict(sorted(data.items()))

def candidate_rules():
    return [{"lookback":lb,"min_return_pct":pct,"min_volume":vol}
            for lb in (3,5,10,20) for pct in (-10,-5,0,3,8)
            for vol in (0,100000)]

def frozen_train(data,cutoff,min_events=25):
    """Single chronological scan of observed historical sessions for every rule.

    Event membership matches the former per-rule/per-ticker scan. No
    post-cutoff prices contribute to ranking; no sparse security lookback.
    """
    dates=[d for d in sorted(data) if d<=cutoff]
    if len(dates)<120: raise ValueError("Insufficient pre-cutoff history")
    split=int(len(dates)*.7)
    segments=[defaultdict(list),defaultdict(list)]
    rules=candidate_rules()
    historical=defaultdict(lambda: deque(maxlen=21))
    for idx,day in enumerate(dates):
        bars=data[day]
        for code,b in bars.items():
            historical[code].append((idx,b))
        if idx+2>=len(dates):
            continue
        tomorrow=data[dates[idx+1]]
        after=data[dates[idx+2]]
        segment=0 if idx<split else 1
        if segment==0 and idx+2>=split:
            continue
        for code,b in bars.items():
            if risk_as_of_close(code,day):continue
            b1=tomorrow.get(code)
            b2=after.get(code)
            if (b1 is None or b2 is None or b1.open<=0
                    or b2.open<=0):
                continue
            h=historical[code]
            # Previous day and n-day lookback must all be real market
            # sessions, not merely the previous n observations for a ticker.
            pct_by_lb={}
            for lb in (3,5,10,20):
                if len(h)<lb+1 or h[-1-lb][0]!=idx-lb:
                    continue
                previous=h[-1-lb][1].adj_close
                if previous>0:
                    pct_by_lb[lb]=(b.adj_close/previous-1)*100
            if not pct_by_lb:
                continue
            result=(b2.open/b1.open-1)*100
            for rule_idx,rule in enumerate(rules):
                lb=rule["lookback"]
                if (lb in pct_by_lb and pct_by_lb[lb]>=rule["min_return_pct"]
                        and b.volume>=rule["min_volume"]):
                    segments[segment][rule_idx].append(result)
    eligible=[]
    for idx,rule in enumerate(rules):
        a=segments[0][idx]
        b=segments[1][idx]
        if len(a)<min_events or len(b)<max(8,min_events//3):
            continue
        ma,mb=mean(a),mean(b)
        eligible.append((min(ma,mb),rule,len(a),len(b),ma,mb))
    eligible.sort(key=lambda p:p[0],reverse=True)
    return eligible

def replay(data,rule,cutoff=CUTOFF,start=START,initial=500000,lot=100,allocation=100000,hold_days=5,fee_rate=.001,corporate_actions=None,slippage_rate=0.0,tax_rate=0.0,max_positions=5,stop_loss_pct=None,take_profit_pct=None,trailing_stop_pct=None,take_profit_band=None,max_hold_at_open=False):
    """Long-only historical paper account. Corporate events must be supplied explicitly.

    corporate_actions: {date: {code: {"split_ratio": positive number,
                     "cash_dividend_per_share": nonnegative number}}}.
    The split event is applied before OPEN orders on the effective date.
    Dividend cash is credited on the supplied *payment* date, not ex-date.
    Missing events are not inferred from adjustment factors. Report is provisional.
    """
    if not (initial > 0 and isinstance(lot,int) and lot > 0 and allocation > 0
            and isinstance(hold_days,int) and hold_days > 0
            and isinstance(max_positions,int) and max_positions > 0
            and 0 <= fee_rate < 1 and 0 <= slippage_rate < 1 and 0 <= tax_rate < 1):
        raise ValueError("Invalid long-only paper-account parameters")
    if not all(v is None or (isinstance(v,(int,float)) and 0 < v < float("inf"))
               for v in (stop_loss_pct,take_profit_pct,trailing_stop_pct)):
        raise ValueError("Exit percentage thresholds must be positive and finite")
    if take_profit_band is not None:
        if (not isinstance(take_profit_band,(tuple,list))
                or len(take_profit_band)!=2
                or any(not isinstance(x,(int,float)) or not math.isfinite(x)
                       for x in take_profit_band)
                or not 0 < take_profit_band[0] < take_profit_band[1] < 100):
            raise ValueError("Invalid closing-profit band")
        if take_profit_pct is not None:
            raise ValueError("Profit band cannot be combined with profit threshold")
    if not isinstance(max_hold_at_open,bool):
        raise ValueError("max_hold_at_open must be bool")
    corporate_actions=corporate_actions or {}
    dates=sorted(data)
    if cutoff not in dates: raise ValueError("Cutoff trading session missing")
    if start<=cutoff: raise ValueError("Replay must start after training cutoff")
    if start not in dates or dates[dates.index(cutoff)+1] != start:
        raise ValueError("Start must equal the first market session after cutoff")
    unknown_days=set(corporate_actions)-set(dates)
    if unknown_days: raise ValueError("Corporate actions must map to market sessions")
    hist=defaultdict(lambda: deque(maxlen=int(rule.get('lookback',5))+1))
    cash=float(initial);positions={};queue=[];ledger=[];daily=[]
    # A corporate event must not be assigned to holdings created after entitlement.
    # For dividends, entitlement_date (ex-date prior close) is mandatory.
    dividend_entitled={}
    entitlement_dates={(code,event["entitlement_date"]) for by_code in corporate_actions.values()
                       for code,event in by_code.items()
                       if "cash_dividend_per_share" in event and "entitlement_date" in event}
    realized_pnl=0.0
    known_dividends=0.0
    risk_buy_skips=0
    risk_sell_requests=0
    for n,day in enumerate(dates):
        bars=data[day]
        # Process entitlement at the close of the supplied trading session,
        # never from data observed later. See capture after close below.
        # Apply only sourced and explicitly supplied corporate actions.
        for code,event in corporate_actions.get(day,{}).items():
            pos=positions.get(code)
            if "split_ratio" in event:
                ratio=event["split_ratio"]
                if not (isinstance(ratio,(int,float)) and 0 < ratio < float("inf")):
                    raise ValueError("Invalid split ratio")
                if pos is not None:
                    new_qty=pos["qty"]*ratio
                    if abs(new_qty-round(new_qty))>1e-8:
                        raise ValueError("Fractional share cash-out requires an explicit event")
                    pos["qty"]=int(round(new_qty))
                    pos["entry_price"]/=ratio
                    pos["peak_close"]/=ratio
                    ledger.append({"date":day,"code":code,"side":"ACTION","status":"SPLIT","ratio":ratio,"qty":pos["qty"]})
            if "cash_dividend_per_share" in event:
                entitlement=event.get("entitlement_date")
                if entitlement is None or entitlement >= day or entitlement not in dates:
                    raise ValueError("Dividend requires a prior observed entitlement date")
                entitled_qty=dividend_entitled.get((code,entitlement),0)
                if not entitled_qty:
                    ledger.append({"date":day,"code":code,"side":"ACTION","status":"NO_DIVIDEND_ENTITLEMENT"})
                    continue
                amount=event["cash_dividend_per_share"]
                if not (isinstance(amount,(int,float)) and 0 <= amount < float("inf")):
                    raise ValueError("Invalid dividend")
                gross=entitled_qty*amount
                net=gross*(1-tax_rate)
                cash+=net
                known_dividends+=net
                ledger.append({"date":day,"code":code,"side":"ACTION","status":"DIVIDEND","gross":round(gross,2),"net":round(net,2),"net_credit":net})
        # At the first replay open: execute Jan30-close orders from Jan30 signal.
        pending_sell_retries=[]
        if day>cutoff and day>=start:
            for order in sorted(queue,key=lambda o:0 if o["side"]=="SELL" else 1):
                code=order["code"];b=bars.get(code)
                if not b or not math.isfinite(b.open) or b.open<=0 or not math.isfinite(b.volume) or b.volume<=0:
                    ledger.append({"date":day,"code":code,"side":order["side"],"status":"NO_OPEN"})
                    # Do not silently cancel the liquidation request while held.
                    # Retry at a later *observable* market open, not at a fake price.
                    if order["side"]=="SELL" and code in positions:
                        pending_sell_retries.append(order)
                    continue
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
                                   "signal_reason":order.get("reason","UNKNOWN"),
                                   "tax":round(tax,2),"realized_pnl":round(received-pos["cost"],2),"net_credit":received})
                else:
                    # Do not fill a queued BUY after a known risk notice, even
                    # if the signal preceded the notice.
                    if risk_as_of_open(code,day):
                        risk_buy_skips+=1
                        continue
                    if code in positions or len(positions)>=max_positions:continue
                    limit=min(cash,allocation)
                    execution_price=b.open*(1+slippage_rate)
                    qty=int(limit/(execution_price*(1+fee_rate))//lot)*lot
                    if qty<lot:continue
                    spent=qty*execution_price*(1+fee_rate)
                    if spent > cash+1e-8: raise AssertionError("Insufficient cash")
                    cash-=spent
                    positions[code]={"qty":qty,"cost":spent,"index":n,
                                     "entry_price":execution_price,
                                     "peak_close":execution_price}
                    ledger.append({"date":day,"code":code,"side":"BUY","qty":qty,"price":round(execution_price,4),"total_debit":spent})
        queue=pending_sell_retries
        for code,b in bars.items():hist[code].append(b)
        for code,pos in positions.items():
            if (code,day) in entitlement_dates:
                dividend_entitled[(code,day)]=pos["qty"]
        if day<cutoff:continue
        # Decisions at CLOSE, after that session has become observable.
        exiting={order["code"] for order in pending_sell_retries}
        for code,pos in positions.items():
            if code in exiting:continue
            # A published listing-risk notice creates an EXIT request for
            # the next observable open. Never fabricate the actual fill.
            if risk_as_of_close(code,day):
                queue.append({"side":"SELL","code":code,"reason":"KNOWN_JPX_LISTING_RISK"})
                exiting.add(code)
                risk_sell_requests+=1
                continue
            observed=bars.get(code)
            if observed is None or not math.isfinite(observed.close) or observed.close<=0:
                # Unknown quote cannot trigger a paper exit using a future price.
                continue
            entry=pos["entry_price"]
            peak=pos["peak_close"]
            close=observed.close
            pos["peak_close"]=max(peak,close)
            reason=None
            # Day-30 OPEN exits require a queue from day-29 CLOSE.
            # Existing frozen legacy backtests keep their original timing.
            if n-pos["index"] >= hold_days-(2 if max_hold_at_open else 1):
                reason="MAX_HOLD"
            elif (take_profit_band is not None
                  and take_profit_band[0] <=
                      100*(close/entry-1) < take_profit_band[1]):
                reason="TAKE_PROFIT_BAND"
            elif stop_loss_pct is not None and close<=entry*(1-stop_loss_pct/100):
                reason="STOP_LOSS"
            elif take_profit_pct is not None and close>=entry*(1+take_profit_pct/100):
                reason="TAKE_PROFIT"
            elif trailing_stop_pct is not None and close<=pos["peak_close"]*(1-trailing_stop_pct/100):
                reason="TRAILING_STOP"
            if reason is not None:
                queue.append({"side":"SELL","code":code,"reason":reason})
                exiting.add(code)
        # Prioritize the strongest observable signal, not alphabetic ticker order.
        # Never inspect next-session prices while ranking today's candidates.
        lookback=int(rule.get("lookback",5))
        ranked=[]
        for code,b in bars.items():
            if code in positions or code in exiting or not math.isfinite(b.volume) or b.volume<=0 or not math.isfinite(b.adj_close) or b.adj_close<=0:
                continue
            history=hist[code]
            # Never treat sparse per-security rows as consecutive sessions.
            if (n < lookback or len(history) < lookback+1
                    or history[-1-lookback].date != dates[n-lookback]):
                continue
            if not rule_matches(history,rule):
                continue
            if risk_as_of_close(code,day):
                risk_buy_skips+=1
                continue
            strength=(history[-1].adj_close/history[-1-lookback].adj_close-1)*100
            ranked.append((-strength,code))
        ranked.sort()  # stable tie-break by code
        candidates=[code for _,code in ranked]
        for code in candidates[:10]:
            queue.append({"side":"BUY","code":code})
        if day>=start:
            if (cash < -0.0001 or any(x["qty"]<=0 for x in positions.values())
                    or len(positions)>max_positions):
                raise AssertionError("Non-cash or short position")
            if all(code in bars and math.isfinite(bars[code].close) and bars[code].close > 0 for code in positions):
                value=cash+sum(pos["qty"]*bars[code].close for code,pos in positions.items())
            else:value=None
            daily.append({"date":day,"cash":round(cash,2),"total_equity":round(value,2) if value is not None else None,
                          "holdings":len(positions)})
    # Aggregate observability for UNKNOWN mark-to-market outcomes. Never
    # convert a missing quote to zero or a stale close without a policy.
    valuation_gaps=[d["date"] for d in daily if d["total_equity"] is None]
    final_session=dates[-1] if dates else None
    final_missing_prices=sum(
        1 for code in positions if code not in data[final_session]
        or not math.isfinite(data[final_session][code].close) or data[final_session][code].close<=0) if final_session else 0
    # A stale quote is only an INDICATIVE scenario, never an actual final quote.
    # This exposes a usable estimate while preserving official final_equity=None.
    last_known_close={}
    held_codes=set(positions)
    for observed_day in dates:
        for ticker,bar in data[observed_day].items():
            if ticker in held_codes and math.isfinite(bar.close) and bar.close>0:
                last_known_close[ticker]=(observed_day,bar.close)
    stale_marks=[]
    indicative_equity=cash
    missing_stale_marks=0
    for ticker,pos in positions.items():
        quote=data[final_session].get(ticker) if final_session else None
        if quote is not None and math.isfinite(quote.close) and quote.close>0:
            indicative_equity+=pos["qty"]*quote.close
        elif ticker in last_known_close:
            quoted_day,stale_price=last_known_close[ticker]
            indicative_equity+=pos["qty"]*stale_price
            stale_marks.append({"last_quote_date":quoted_day,
                                "stale_calendar_days":(__import__("datetime").date.fromisoformat(final_session)-
                                      __import__("datetime").date.fromisoformat(quoted_day)).days,
                                "notional_value":round(pos["qty"]*stale_price,2)})
        else:
            missing_stale_marks+=1
    last_known_estimate=(round(indicative_equity,2) if missing_stale_marks==0 else None)
    known_values=[day["total_equity"] for day in daily]
    if all(v is not None for v in known_values):
        high=initial
        max_dd=0.0
        for value in known_values:
            high=max(high,value)
            max_dd=max(max_dd,(high-value)/high*100)
    else:
        max_dd=None
    # Account identity: final assets equal contributed capital + closed-trade
    # realized profits + dividends + unsold mark-to-market gains.
    final_equity=known_values[-1] if known_values else None
    unrealized=sum((positions[code]["qty"]*data[dates[-1]][code].close-
                    positions[code]["cost"]) for code in positions) if final_equity is not None else None
    if final_equity is not None and abs(final_equity-(initial+realized_pnl+known_dividends+unrealized))>0.03:
        raise AssertionError("Portfolio accounting identity failed")
    cash_and_shares_check=reconcile(initial,ledger,positions,cash)
    return {"cash":round(cash,2),"held":positions,"fills":ledger,"equity":daily,
            "ledger_audit":cash_and_shares_check,
            "listing_risk_screen":{"source":"VERIFIED_JPX_SUBSET",
               "historical_universe_coverage":"INCOMPLETE",
               "buy_signals_or_fills_skipped":risk_buy_skips,
               "risk_exit_requests":risk_sell_requests,
               "warning":"Only three manually verified JPX histories included; no comprehensive as-of market registry."},
            "final_equity":known_values[-1] if known_values else None,
            "realized_pnl":round(realized_pnl,2),
            "unrealized_pnl":round(unrealized,2) if unrealized is not None else None,
            "known_net_dividends":round(known_dividends,2),
            "max_drawdown_pct":round(max_dd,4) if max_dd is not None else None,
            "unfilled_after_final_session":queue,
            "valuation_diagnostics":{
                "unpriced_days":len(valuation_gaps),
                "first_unpriced_day":valuation_gaps[0] if valuation_gaps else None,
                "last_unpriced_day":valuation_gaps[-1] if valuation_gaps else None,
                "held_positions_final":len(positions),
                "held_positions_without_final_close":final_missing_prices,
                "final_equity_available":final_equity is not None,
                "indicative_last_known_equity":last_known_estimate,
                "indicative_valuation_method":"MOST_RECENT_KNOWN_CLOSE_UNVERIFIED_NOT_TRADABLE",
                "indicative_stale_positions":len(stale_marks),
                "indicative_missing_price_positions":missing_stale_marks,
                "indicative_oldest_quote_calendar_days":max(
                    (x["stale_calendar_days"] for x in stale_marks),default=0),
                "requires_source_data_review":bool(valuation_gaps)},
            "validation_status":"PROVISIONAL_UNVERIFIED",
            "accounting_note":"Corporate actions require complete dated external events; no automatic inference."}

def experiment(data,cutoff=CUTOFF,start=START,fixed_rule=None):
    """Fixed-rule mode replays a PREVIOUSLY selected rule; it never re-trains."""
    if fixed_rule is None:
        candidates=frozen_train(data,cutoff)
        if not candidates: return {"status":"no_qualifying_train_rule","cutoff":cutoff,"start":start,"rules_tested":len(candidate_rules())}
        score,rule,n1,n2,r1,r2=candidates[0]
        training={"split1_trades":n1,"split2_trades":n2,"mean_pct1":round(r1,3),"mean_pct2":round(r2,3)}
        provenance="TRAINED_AS_OF_CUTOFF"
    else:
        if not isinstance(fixed_rule,dict) or set(fixed_rule)!={"lookback","min_return_pct","min_volume"} or fixed_rule not in candidate_rules():
            raise ValueError("Fixed rule must exactly match a supported candidate")
        rule=fixed_rule
        training=None
        provenance="EXTERNAL_PRIOR_RUN_NOT_RETRAINED"
    simulation=replay(data,rule,cutoff,start)
    return {"status":"completed","cutoff":cutoff,"start":start,"data_last_date":max(data),
            "rules_tested":0 if fixed_rule is not None else len(candidate_rules()),
            "selection_provenance":provenance,
            "selected_rule_frozen_at_cutoff":rule,
            "training_only":training,
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
    ap.add_argument("--fixed-rule-json",help="Previously frozen candidate rule; skip costly retraining")
    a=ap.parse_args()
    fixed_rule=json.loads(a.fixed_rule_json) if a.fixed_rule_json else None
    data=load_private_neon() if a.from_neon else load_bars(a.root)
    result=experiment(data,a.cutoff,a.start,fixed_rule=fixed_rule)
    with open(a.out,"w",encoding="utf-8") as fh:json.dump(result,fh,ensure_ascii=False,indent=2)
    print(json.dumps({"status":result["status"],"cutoff":a.cutoff,"start":a.start,
        "rule_count":result["rules_tested"],"selected_rule":result.get("selected_rule_frozen_at_cutoff"),
        "paper_fills":len(result.get("paper_result",{}).get("fills",[])),
        "result_file":a.out},ensure_ascii=False))
if __name__=="__main__":main()
