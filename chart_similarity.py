#!/usr/bin/env python3
"""Point-in-time historical chart-shape nearest-neighbour research.

Only descriptive similarity statistics, never future-stock probabilities.
Reference curves can be price series or bottom-up screenshot trace points.
Raw licensed bars and stock-level examples remain private; don't publish JSON.
"""
import argparse
import json
import math
from collections import defaultdict

HORIZONS = (5, 10, 20)

def interpolate(seq, count=20):
    seq = [float(v) for v in seq]
    if len(seq)<3 or count<3 or not all(math.isfinite(v) for v in seq):
        raise ValueError("Reference curve needs at least three finite points")
    if len(seq)==count:
        return seq
    out=[]
    for i in range(count):
        pos=i*(len(seq)-1)/(count-1)
        left=int(pos);right=min(left+1,len(seq)-1)
        out.append(seq[left]+(seq[right]-seq[left])*(pos-left))
    return out

def fingerprint(values, count=20):
    """Z-normalization matches relative shape, not absolute stock prices."""
    seq=interpolate(values,count)
    avg=sum(seq)/len(seq)
    var=sum((v-avg)**2 for v in seq)/len(seq)
    if var<1e-14:
        raise ValueError("Flat screenshot/chart has no distinguishable shape")
    std=math.sqrt(var)
    return [(v-avg)/std for v in seq]

def rms_distance(a,b):
    if len(a)!=len(b):raise ValueError("Mismatched curve lengths")
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))

def wilson(wins, observed, z=1.96):
    if observed==0:return None
    p=wins/observed;denom=1+z*z/observed
    center=(p+z*z/(2*observed))/denom
    half=z*math.sqrt(p*(1-p)/observed+z*z/(4*observed*observed))/denom
    return [round(max(0,100*(center-half)),1),round(min(100,100*(center+half)),1)]

def _valid_price(bar):
    price=getattr(bar,"adj_close",None)
    return (price is not None and isinstance(price,(int,float))
            and math.isfinite(price) and price>0)

def find_matches(data, reference, lookback=20, horizons=HORIZONS,
                 top_k=30, as_of=None, skip_code=None):
    """Scan only completed and continuous global-market sessions.

    Result examples have verified observed prices through max(horizons) after
    their matched pattern; they never borrow tomorrow's price for matching.
    A symbol cannot contribute overlapping windows to the ranked sample.
    """
    if not isinstance(lookback,int) or lookback<5 or lookback>120:
        raise ValueError("lookback must be an integer from 5 to 120")
    if not isinstance(top_k,int) or not 1<=top_k<=500:
        raise ValueError("top_k must be 1..500")
    horizons=tuple(sorted(set(horizons)))
    if not horizons or any(not isinstance(h,int) or h<=0 or h>120 for h in horizons):
        raise ValueError("Invalid horizon")
    days=sorted(d for d in data if as_of is None or d<=as_of)
    if len(days)<lookback+max(horizons):
        raise ValueError("Not enough sessions with observable future outcomes")
    query=fingerprint(reference)
    max_h=max(horizons)
    by_code=defaultdict(list)
    for i,day in enumerate(days):
        for code,bar in data[day].items():
            if _valid_price(bar):
                by_code[code].append((i,bar.adj_close))
    shortlist=defaultdict(list)
    eligible=0
    for code,history in by_code.items():
        if skip_code is not None and code==skip_code:
            continue
        # Only full consecutive sessions; missing/suspended rows never padded.
        for end in range(lookback-1,len(history)-max_h):
            full=history[end-lookback+1:end+max_h+1]
            if full[-1][0]-full[0][0]!=len(full)-1:
                continue
            window=[value for _,value in full[:lookback]]
            try:
                shape=fingerprint(window)
            except ValueError:
                continue
            eligible+=1
            distance=rms_distance(query,shape)
            future={}
            at=full[lookback-1][1]
            for horizon in horizons:
                finish=full[lookback-1+horizon][1]
                future[str(horizon)]=round((finish/at-1)*100,4)
            anchor=history[end][0]
            local=shortlist[code]
            gap=lookback+max_h
            overlap=[old for old in local if abs(old[1]-anchor)<gap]
            if overlap:
                if all(distance<old[0] for old in overlap):
                    for old in overlap:local.remove(old)
                else:
                    continue
            local.append((distance,anchor,future))
            if len(local)>20:
                local.sort(key=lambda v:v[0])
                del local[20:]
    candidates=sorted(
        ((distance,code,anchor,future) for code,local in shortlist.items()
         for distance,anchor,future in local),
        key=lambda row:(row[0],row[1],row[2]))
    selected=[{"code":code,"match_date":days[anchor],
               "shape_distance":round(distance,6),"future_returns_pct":future}
              for distance,code,anchor,future in candidates[:top_k]]
    stats={}
    for h in horizons:
        returns=[r["future_returns_pct"][str(h)] for r in selected]
        wins=sum(x>0 for x in returns)
        flats=sum(x==0 for x in returns)
        n=len(returns)
        sorted_returns=sorted(returns)
        middle=(sorted_returns[(n-1)//2]+sorted_returns[n//2])/2 if n else None
        stats[str(h)]={
            "samples":n,
            "up":wins,"down":sum(x<0 for x in returns),"flat":flats,
            "up_pct":round(wins/n*100,1) if n else None,
            "down_pct":round(sum(x<0 for x in returns)/n*100,1) if n else None,
            "wilson_95_up_pct":wilson(wins,n),
            "median_return_pct":round(middle,3) if n else None,
            "avg_return_pct":round(sum(returns)/n,3) if n else None}
    return {"status":"HISTORICAL_DESCRIPTIVE_ONLY",
            "as_of":days[-1],"lookback":lookback,
            "horizons":list(horizons),"candidate_windows_scanned":eligible,
            "independent_matches":len(selected),"requested_matches":top_k,
            "shape_distance_metric":"ZNORMALIZED_LEVEL_RMSE",
            "statistics":stats,"matches":selected,
            "limitations":[
                "Historical similar-pattern frequency is NOT a calibrated probability of future price rises.",
                "Adjusted closes may be retrospectively changed by corporate actions; action provenance has not been verified.",
                "No brokerage execution, dividends, tax, fees, liquidity or slippage model.",
                "Top-K sampling, market regimes, delistings and available-archive coverage can bias observed frequencies.",
                "Screenshot traces capture relative shape only; cannot infer price scale or exact candle data."
            ]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--curve-json",required=True,
                        help="Private JSON array of left-to-right numerical curve heights (bottom-up)")
    parser.add_argument("--from-neon",action="store_true")
    parser.add_argument("--root",default="archive/daily")
    parser.add_argument("--lookback",type=int,default=20)
    parser.add_argument("--top",type=int,default=30)
    parser.add_argument("--as-of")
    parser.add_argument("--out",default="private-chart-neighbors.json")
    args=parser.parse_args()
    with open(args.curve_json,encoding="utf-8") as fh:
        values=json.load(fh)
    if args.from_neon:
        from february_walkforward import load_private_neon
        data=load_private_neon()
    else:
        from walkforward_backtest import load_bars
        data=load_bars(args.root)
    result=find_matches(data,values,lookback=args.lookback,as_of=args.as_of,top_k=args.top)
    with open(args.out,"w",encoding="utf-8") as fh:
        json.dump(result,fh,ensure_ascii=False,indent=2)
    print(json.dumps({"status":result["status"],
        "candidate_windows_scanned":result["candidate_windows_scanned"],
        "matches":result["independent_matches"],"statistics":result["statistics"]},
        ensure_ascii=False))

if __name__=="__main__":
    main()
