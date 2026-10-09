#!/usr/bin/env python3
"""Offline historical pattern discovery, chronological holdout and delayed-data watchlist.
No brokerage orders, no publication of licensed raw market records.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from walkforward_backtest import load_bars

# Conditions use ONLY values through the signal day's closing auction.
PATTERNS = [
    ("return_5d", 5, -10, -5), ("return_5d", 5, -5, 0),
    ("return_5d", 5, 0, 5), ("return_5d", 5, 5, 10),
    ("return_5d", 5, 10, None),
    ("return_20d", 20, -20, -10), ("return_20d", 20, -10, 0),
    ("return_20d", 20, 0, 10), ("return_20d", 20, 10, 20),
    ("return_20d", 20, 20, None),
    ("volume_ratio_5d", 5, 2, None), ("volume_ratio_5d", 5, 3, None),
    ("rise_streak", 3, 3, None), ("rise_streak", 5, 5, None),
    ("fall_streak", 3, 3, None), ("fall_streak", 5, 5, None),
]
HORIZONS=(1,5,20)
def band(v,lo,hi):
    return v is not None and (lo is None or v>=lo) and (hi is None or v<hi)

def signal_features(bars,index):
    b=bars[index]
    out={}
    for days in (5,20):
        if index>=days and bars[index-days].adj_close>0:
            out[f"return_{days}d"]=(b.adj_close/bars[index-days].adj_close-1)*100
    if index>=5:
        baseline=mean(x.volume for x in bars[index-5:index])
        if baseline>0: out["volume_ratio_5d"]=b.volume/baseline
    up=down=0
    for j in range(index,0,-1):
        prior=bars[j-1].adj_close
        if prior<=0: break
        pct=bars[j].adj_close/prior-1
        if pct>0 and down==0:up+=1
        elif pct<0 and up==0:down+=1
        else:break
    out["rise_streak"]=up
    out["fall_streak"]=down
    return out

def pattern_name(p):
    field,_,lo,hi=p
    return f"{field}:{lo if lo is not None else '*'}..{hi if hi is not None else '*'}"

def discover(data,min_events=30,top=15):
    dates=sorted(data)
    if len(dates)<100:raise ValueError("Need >=100 daily sessions to preserve chronological test sample")
    # Strict chronological partition: first 60% discovery, next 20% validation,
    # final 20% test. Entire market uses SAME boundaries.
    n=len(dates);train_end=int(n*.6);valid_end=int(n*.8)
    end_dates={"discovery":dates[train_end-1],"validation":dates[valid_end-1],"test":dates[-1]}
    series=defaultdict(list)
    for day in dates:
        for code,b in data[day].items():series[code].append(b)
    bucket=defaultdict(list);last_candidates={}
    for code,bars in series.items():
        last_features=signal_features(bars,len(bars)-1) if bars else {}
        last_candidates[code]=(bars[-1].date,last_features)
        for i in range(20,len(bars)-max(HORIZONS)):
            signal=bars[i]
            # Never trade at signal close: hypothetical return is next session OPEN
            # to future OPEN for the required holding horizon.
            if bars[i+1].open<=0:continue
            partition="discovery" if signal.date<=end_dates["discovery"] else "validation" if signal.date<=end_dates["validation"] else "test"
            feats=signal_features(bars,i)
            for p in PATTERNS:
                if not band(feats.get(p[0]),p[2],p[3]):continue
                for horizon in HORIZONS:
                    if i+1+horizon>=len(bars):continue
                    exit_bar=bars[i+1+horizon]
                    if exit_bar.open<=0:continue
                    ret=(exit_bar.open/bars[i+1].open-1)*100
                    bucket[(pattern_name(p),partition,horizon)].append(ret)
    # Select using ONLY discovery+validation. Holdout TEST scores are purely audit.
    ranked=[]
    def stats(values):
        if not values:return None
        return {"n":len(values),"win_rate":round(sum(v>0 for v in values)/len(values)*100,2),
                "mean_pct":round(mean(values),3),"median_pct":round(median(values),3)}
    for p in PATTERNS:
        name=pattern_name(p)
        for horizon in HORIZONS:
            a=stats(bucket[name,"discovery",horizon])
            v=stats(bucket[name,"validation",horizon])
            if not a or not v or a["n"]<min_events or v["n"]<max(10,min_events//3):continue
            ranked.append({"pattern":name,"horizon_sessions":horizon,"discovery":a,
                           "validation":v,"test":stats(bucket[name,"test",horizon]),
                           "selection_score":round(min(a["mean_pct"],v["mean_pct"]),3)})
    ranked.sort(key=lambda x:(x["selection_score"],x["validation"]["n"]),reverse=True)
    chosen=ranked[:top]
    latest=dates[-1]
    matches=[]
    chosen_names={r["pattern"] for r in chosen}
    for code,(date,feats) in last_candidates.items():
        if date!=latest:continue
        match=[pattern_name(p) for p in PATTERNS if pattern_name(p) in chosen_names and band(feats.get(p[0]),p[2],p[3])]
        if match:matches.append({"code":code,"as_of":date,"matched_patterns":match})
    matches.sort(key=lambda r:(-len(r["matched_patterns"]),r["code"]))
    return {"sessions":n,"data_last_date":latest,"holdout_boundaries":end_dates,
            "all_pattern_horizon_combinations":len(PATTERNS)*len(HORIZONS),
            "selected_patterns":chosen,"historical_date_watchlist":matches,
            "disclaimer":"Not live stock picks: free J-Quants history is delayed. Same-security adjacent signals are correlated; test results are descriptive, not independent forecasts. No costs, slippage, corporate-action handling or survivorship protection in this research screen."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="archive/daily")
    ap.add_argument("--out",default="private-pattern-results.json")
    ap.add_argument("--min-events",type=int,default=30)
    a=ap.parse_args()
    result=discover(load_bars(a.root),a.min_events)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"sessions":result["sessions"],"last_date":result["data_last_date"],
                      "selected_count":len(result["selected_patterns"]),
                      "matched_codes":len(result["historical_date_watchlist"]),
                      "saved_private_result":a.out},ensure_ascii=False))
if __name__=="__main__":main()
