#!/usr/bin/env python3
"""V2: Predeclared downside-first price-pattern research, 1..30 market sessions.

Historical observed frequencies only, NOT calibrated forecast probabilities.
Detect patterns at end-of-day from trailing data; labels from future sessions.
No position sizing, brokerage execution, or imaginary delisting fills.
"""
import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from jpx_market_risk import risk_as_of_close

VERSION="downside-conditions-v2"
HORIZONS=range(1,31)
LOOKBACK=20
COOLDOWN=30
MIN_OBS=200
MIN_STOCKS=50
LEVELS=(3,5,10)
# This is a finite, transparently predeclared catalog. No parameter mining on
# future returns when selecting a pattern's conditions.
CATALOG={"BASE":("reference","比較母集団（21営業日の連続観測）")}
for days in (1,3,5,10,20):
    for pct in (1,3,5,10):
        for direction in ("DOWN","UP"):
            code=f"R{days:02d}_{direction}{pct:02d}"
            CATALOG[code]=("return",f"過去{days}営業日で{'下落' if direction=='DOWN' else '上昇'}{pct}%以上")
for days in (2,3,4,5,6,7):
    for direction in ("DOWN","UP"):
        CATALOG[f"STREAK{days}_{direction}"]=("streak",f"{days}営業日連続{'下落' if direction=='DOWN' else '上昇'}")
for days in (5,10,20):
    for direction in ("LOW","HIGH"):
        CATALOG[f"{direction}{days}"]=("extreme",f"過去{days}日終値{'安値割れ' if direction=='LOW' else '高値更新'}")
for short,long in ((3,5),(5,10),(5,20),(10,20)):
    for direction in ("BEAR","BULL"):
        CATALOG[f"MA{short}_{long}_{direction}"]=("trend",f"{short}日平均が{long}日平均より{'低い' if direction=='BEAR' else '高い'}")
for direction in ("DEATH","GOLDEN"):
    CATALOG[f"MA5_20_{direction}"]=("trend",f"5日と20日平均の{'デッド' if direction=='DEATH' else 'ゴールデン'}クロス")
for pct in (20,40):
    for side in ("BOTTOM","TOP"):
        CATALOG[f"RANGE_{side}{pct}"]=("range",f"20日価格レンジの{'下' if side=='BOTTOM' else '上'}位{pct}%以内")
for pct in (5,10,20):
    CATALOG[f"DRAWDOWN{pct}"]=("range",f"20日高値から{pct}%以上下落")
    CATALOG[f"REBOUND{pct}"]=("range",f"20日安値から{pct}%以上上昇")
for days in (5,10,20):
    for level,condition in (("LOW","1%未満"),("HIGH","3%以上"),("EXTREME","5%以上")):
        CATALOG[f"VOLAT{days}_{level}"]=("volatility",f"過去{days}日の日次変化標準偏差が{condition}")
for ratio in (1.5,2.0,3.0):
    for direction in ("DOWN","UP"):
        CATALOG[f"VOLUME{str(ratio).replace('.','')}_{direction}"]=("volume",f"出来高が直前5日平均の{ratio}倍以上かつ当日{'下落' if direction=='DOWN' else '上昇'}")
for direction in ("DOWN","UP"):
    CATALOG[f"VOLUME_DRY_{direction}"]=("volume",f"出来高が直前5日平均の半分以下かつ当日{'下落' if direction=='DOWN' else '上昇'}")
for key,label in (
    ("BEAR_BODY","長い陰線"),
    ("BULL_BODY","長い陽線"),
    ("UPPER_WICK","長い上ヒゲ"),
    ("LOWER_WICK","長い下ヒゲ"),
    ("CLOSE_LOW","日中安値付近で引け"),
    ("CLOSE_HIGH","日中高値付近で引け"),
    ("GAP_DOWN","前終値から1%以上下方ギャップ"),
    ("GAP_UP","前終値から1%以上上方ギャップ"),
    ("BEAR_ENGULF","陰線包み足（前日実体を包む）"),
    ("BULL_ENGULF","陽線包み足（前日実体を包む）"),
    ("DOJI","寄引同事線（実体がレンジの10%以内）"),
    ("INSIDE","前日高値・安値の内側に収まる"),
    ("OUTSIDE","前日高値・安値を両方更新"),
):
    CATALOG[key]=("candlestick",label)
_COMBOS={
    "HIGH20_VOL_UP":("HIGH20","VOLUME20_UP"),
    "HIGH20_UPPER_WICK":("HIGH20","UPPER_WICK"),
    "HIGH20_GAP_UP":("HIGH20","GAP_UP"),
    "MA_BEAR_DOWN3":("MA5_20_BEAR","STREAK3_DOWN"),
    "MA_BULL_DOWN3":("MA5_20_BULL","STREAK3_DOWN"),
    "MA_BULL_HIGH20":("MA5_20_BULL","HIGH20"),
    "MA_BEAR_LOW20":("MA5_20_BEAR","LOW20"),
    "LOW20_VOL_DOWN":("LOW20","VOLUME20_DOWN"),
    "LOW20_LOWER_WICK":("LOW20","LOWER_WICK"),
    "DOWN5_HIGHVOL":("R05_DOWN05","VOLAT5_HIGH"),
    "UP5_HIGHVOL":("R05_UP05","VOLAT5_HIGH"),
    "MA_BEAR_VOL_DOWN":("MA5_20_BEAR","VOLUME20_DOWN"),
}
for name,parts in _COMBOS.items():
    CATALOG[name]=("intersection","かつ".join(CATALOG[p][1] for p in parts))
assert len(CATALOG)==len(set(CATALOG))

def _safe(x):
    return isinstance(x,(int,float)) and math.isfinite(x)

def adjusted(bar):
    """Return (adjusted-close, volume, adjusted-open,high,low) or None.

    Today's historical price adjustment factor is applied to OHLC; corporate
    action provenance remains unverified and cannot be treated as authoritative.
    """
    if bar is None:return None
    try:
        adj=float(bar.get("adjusted_close"))
        c=float(bar.get("close_price"))
        v=float(bar.get("volume"))
    except (ValueError,TypeError):return None
    if not all(map(_safe,(adj,c,v))) or min(adj,c)<=0 or v<0:return None
    try:
        op=float(bar.get("open_price"))
        hi=float(bar.get("high_price"))
        lo=float(bar.get("low_price"))
        scale=adj/c
        if not all(map(_safe,(op,hi,lo))) or not (0<lo<=min(op,c)<=max(op,c)<=hi):
            return (adj,v,None,None,None)
        return (adj,v,op*scale,hi*scale,lo*scale)
    except (ValueError,TypeError):
        return (adj,v,None,None,None)

def detect(bars):
    """At most 21 past/current global market observations, no future reads.

    Pattern not observed != pattern fails: OHLC patterns require valid H/L data.
    """
    if len(bars)!=21:raise ValueError("Require 21 past market-session bars")
    obs=[adjusted(b) for b in bars]
    if any(b is None or b[1]<=0 for b in obs):
        return set()
    p=[x[0] for x in obs];v=[x[1] for x in obs]
    ret={n:(p[-1]/p[-1-n]-1)*100 for n in (1,3,5,10,20)}
    found={"BASE"}
    for n,r in ret.items():
        for pct in (1,3,5,10):
            if r<=-pct:found.add(f"R{n:02d}_DOWN{pct:02d}")
            if r>=pct:found.add(f"R{n:02d}_UP{pct:02d}")
    for n in (2,3,4,5,6,7):
        if all(p[-j]<p[-j-1] for j in range(1,n+1)):found.add(f"STREAK{n}_DOWN")
        if all(p[-j]>p[-j-1] for j in range(1,n+1)):found.add(f"STREAK{n}_UP")
    for n in (5,10,20):
        if p[-1]<min(p[-1-n:-1]):found.add(f"LOW{n}")
        if p[-1]>max(p[-1-n:-1]):found.add(f"HIGH{n}")
    def ma(n,end=None):
        s=p[-n:] if end is None else p[-n-1:-1]
        return sum(s)/n
    for short,long in ((3,5),(5,10),(5,20),(10,20)):
        if ma(short)<ma(long):found.add(f"MA{short}_{long}_BEAR")
        if ma(short)>ma(long):found.add(f"MA{short}_{long}_BULL")
    if ma(5)<ma(20) and ma(5,-1)>=ma(20,-1):
        found.add("MA5_20_DEATH")
    if ma(5)>ma(20) and ma(5,-1)<=ma(20,-1):
        found.add("MA5_20_GOLDEN")
    mi=min(p[-20:]);mx=max(p[-20:])
    pos=(p[-1]-mi)/(mx-mi) if mx>mi else .5
    for threshold in (20,40):
        if pos<=threshold/100:found.add(f"RANGE_BOTTOM{threshold}")
        if pos>=1-threshold/100:found.add(f"RANGE_TOP{threshold}")
    for pct in (5,10,20):
        if p[-1]<=mx*(1-pct/100):found.add(f"DRAWDOWN{pct}")
        if p[-1]>=mi*(1+pct/100):found.add(f"REBOUND{pct}")
    for n in (5,10,20):
        day_ret=[p[-j]/p[-j-1]-1 for j in range(n,0,-1)]
        avg=sum(day_ret)/len(day_ret)
        stdev=math.sqrt(sum((x-avg)**2 for x in day_ret)/n)
        if stdev<.01:found.add(f"VOLAT{n}_LOW")
        if stdev>=.03:found.add(f"VOLAT{n}_HIGH")
        if stdev>=.05:found.add(f"VOLAT{n}_EXTREME")
    volavg=sum(v[-6:-1])/5
    if volavg>0:
        ratio=v[-1]/volavg
        direction="UP" if ret[1]>0 else ("DOWN" if ret[1]<0 else None)
        if direction:
            for level in (1.5,2.0,3.0):
                if ratio>=level:
                    found.add(f"VOLUME{str(level).replace('.','')}_{direction}")
            if ratio<=.5:found.add(f"VOLUME_DRY_{direction}")
    if obs[-1][2] is not None:
        a,b=obs[-1],obs[-2]
        op,hi,lo=a[2:]
        c=p[-1]
        span=hi-lo
        if span>0:
            body=abs(c-op)
            if op>c and body>=.6*span:found.add("BEAR_BODY")
            if c>op and body>=.6*span:found.add("BULL_BODY")
            if hi-max(c,op)>=max(.01*span,2*body):found.add("UPPER_WICK")
            if min(c,op)-lo>=max(.01*span,2*body):found.add("LOWER_WICK")
            if (c-lo)/span<=.1:found.add("CLOSE_LOW")
            if (hi-c)/span<=.1:found.add("CLOSE_HIGH")
            if body/span<=.1:found.add("DOJI")
        if op<=p[-2]*.99:found.add("GAP_DOWN")
        if op>=p[-2]*1.01:found.add("GAP_UP")
        if b[2] is not None:
            prevop,prevhi,prevlo=b[2:]
            if op>=p[-2] and c<op and c<=prevop and prevop<p[-2]:
                found.add("BEAR_ENGULF")
            if op<=p[-2] and c>op and c>=prevop and prevop>p[-2]:
                found.add("BULL_ENGULF")
            if hi<prevhi and lo>prevlo:found.add("INSIDE")
            if hi>prevhi and lo<prevlo:found.add("OUTSIDE")
    for code,parts in _COMBOS.items():
        if all(x in found for x in parts):found.add(code)
    assert found.issubset(CATALOG)
    return found

def blank():
    return {"total":0,"observed":0,"missing":0,"unmatured":0,
            "down":0,"up":0,"flat":0,"loss3":0,"loss5":0,"loss10":0,
            "path_complete":0,"path_unknown":0,"touch3":0,"touch5":0,"touch10":0,
            "sum_return":0.0}

def count_outcomes(totals,code,obs,dates,train_end,holdout_start,symbols):
    by_index=dict(obs)
    last={}
    for t in sorted(by_index):
        if t<LOOKBACK:continue
        day=dates[t]
        if train_end<day<holdout_start:continue
        if risk_as_of_close(code,day):continue
        window=[by_index.get(j) for j in range(t-LOOKBACK,t+1)]
        if any(x is None for x in window):continue
        tags=detect(window)
        segment="train" if day<=train_end else "holdout"
        baseline=adjusted(by_index[t])[0] if tags else None
        for tag in tags:
            if t-last.get((segment,tag),-99999)<COOLDOWN:continue
            last[(segment,tag)]=t
            symbols[(segment,tag)].add(code)
            current_low=math.inf
            complete_path=True
            for h in HORIZONS:
                entry=totals[(segment,tag,h)]
                entry["total"]+=1
                j=t+h
                if j>=len(dates) or (segment=="train" and dates[j]>train_end):
                    entry["unmatured"]+=1
                    continue
                bar=adjusted(by_index.get(j))
                if bar is None:
                    entry["missing"]+=1
                    complete_path=False
                    continue
                outcome=(bar[0]/baseline-1)*100
                entry["observed"]+=1
                if outcome<0:entry["down"]+=1
                elif outcome>0:entry["up"]+=1
                else:entry["flat"]+=1
                entry["sum_return"]+=outcome
                for threshold in LEVELS:
                    if outcome<=-threshold:entry[f"loss{threshold}"]+=1
                if bar[4] is None:
                    complete_path=False
                if complete_path:
                    current_low=min(current_low,bar[4])
                    entry["path_complete"]+=1
                    for threshold in LEVELS:
                        if current_low<=baseline*(1-threshold/100):
                            entry[f"touch{threshold}"]+=1
                else:
                    entry["path_unknown"]+=1

def summarize(totals,symbols,first_day,last_day,train_end,holdout_start):
    rows=[]
    for segment in ("train","holdout"):
        for tag,(family,name) in CATALOG.items():
            unique=len(symbols.get((segment,tag),set()))
            for h in HORIZONS:
                c=totals.get((segment,tag,h),blank()); n=c["observed"]
                assert c["total"]==n+c["missing"]+c["unmatured"]
                assert c["down"]+c["up"]+c["flat"]==n
                assert c["path_complete"]+c["path_unknown"]<=n
                lower,upper=wilson(c["down"],n)
                enough=n>=MIN_OBS and unique>=MIN_STOCKS
                rows.append({
                    "segment":segment,"pattern":tag,"family":family,
                    "horizon":h,"total":c["total"],"observed":n,
                    "missing":c["missing"],"unmatured":c["unmatured"],
                    "unique_symbols":unique,"down":c["down"],"up":c["up"],"flat":c["flat"],
                    "down_pct":round(100*c["down"]/n,3) if n else None,
                    "down_ci95_low":lower,"down_ci95_high":upper,
                    "close_loss3_pct":round(100*c["loss3"]/n,3) if n else None,
                    "close_loss5_pct":round(100*c["loss5"]/n,3) if n else None,
                    "close_loss10_pct":round(100*c["loss10"]/n,3) if n else None,
                    "path_complete":c["path_complete"],
                    "path_unknown":c["path_unknown"],
                    "touch_loss3_pct":round(100*c["touch3"]/c["path_complete"],3)
                        if c["path_complete"] else None,
                    "touch_loss5_pct":round(100*c["touch5"]/c["path_complete"],3)
                        if c["path_complete"] else None,
                    "touch_loss10_pct":round(100*c["touch10"]/c["path_complete"],3)
                        if c["path_complete"] else None,
                    "mean_return_pct":round(c["sum_return"]/n,4) if n else None,
                    "state":"DESCRIPTIVE_UNVERIFIED" if enough else "INSUFFICIENT_EVIDENCE"
                })
    return {
        "version":VERSION,"first_day":first_day,"last_day":last_day,
        "train_end":train_end,"holdout_start":holdout_start,
        "validation_status":"NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED",
        "source_coverage":"JPX_LISTING_RISK_INCOMPLETE",
        "pattern_count":len(CATALOG),"patterns":[
            {"code":k,"family":v[0],"name":v[1]} for k,v in CATALOG.items()],
        "rows":rows
    }

def wilson(wins,n):
    if not n:return (None,None)
    p=wins/n;z=1.96;den=1+z*z/n
    mid=(p+z*z/(2*n))/den
    dist=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (round(100*max(0,mid-dist),2),round(100*min(1,mid+dist),2))

def analyze(data,train_end="2026-01-30",holdout_start="2026-02-02"):
    dates=sorted(data)
    if not dates or train_end>=holdout_start:raise ValueError("Bad boundaries")
    by_code=defaultdict(list)
    for i,day in enumerate(dates):
        for code,bar in data[day].items():by_code[code].append((i,bar))
    totals=defaultdict(blank);symbols=defaultdict(set)
    for code,obs in by_code.items():
        count_outcomes(totals,code,obs,dates,train_end,holdout_start,symbols)
    return summarize(totals,symbols,dates[0],dates[-1],train_end,holdout_start)

def from_neon(conn,train_end,holdout_start):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT trading_date FROM daily_bar ORDER BY trading_date")
        dates=[row[0].isoformat() for row in cur]
    day_idx={day:i for i,day in enumerate(dates)}
    totals=defaultdict(blank);symbols=defaultdict(set)
    processed=0
    with conn.cursor(name="downside_pattern_stream") as cur:
        cur.itersize=10000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,
                       open_price,high_price,low_price,close_price,volume
                       FROM daily_bar ORDER BY security_code,trading_date""")
        active=None;one=[]
        for code,day,adj,op,hi,lo,close,vol in cur:
            if active is not None and code!=active:
                count_outcomes(totals,active,one,dates,train_end,holdout_start,symbols)
                processed+=1
                one=[]
            active=code
            one.append((day_idx[day.isoformat()],{
                "adjusted_close":float(adj) if adj is not None else None,
                "open_price":float(op) if op is not None else None,
                "high_price":float(hi) if hi is not None else None,
                "low_price":float(lo) if lo is not None else None,
                "close_price":float(close) if close is not None else None,
                "volume":float(vol) if vol is not None else None}))
        if active is not None:
            count_outcomes(totals,active,one,dates,train_end,holdout_start,symbols)
            processed+=1
    result=summarize(totals,symbols,dates[0],dates[-1],train_end,holdout_start)
    result["symbols_scanned"]=processed
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--from-neon",action="store_true")
    p.add_argument("--train-end",default="2026-01-30")
    p.add_argument("--holdout-start",default="2026-02-02")
    p.add_argument("--out",help="Private aggregate JSON destination")
    p.add_argument("--write-db",action="store_true")
    args=p.parse_args()
    if not args.from_neon:raise SystemExit("Private Neon is required in this runner")
    import psycopg
    dsn=os.environ.get("DATABASE_URL")
    if not dsn:raise SystemExit("Missing DATABASE_URL")
    with psycopg.connect(dsn,sslmode="require") as conn:
        result=from_neon(conn,args.train_end,args.holdout_start)
        if args.write_db:
            from downside_pattern_storage import store
            store(conn,result)
    if args.out:
        Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),
                                  encoding="utf8")
    print(json.dumps({"version":VERSION,"status":result["validation_status"],
        "pattern_count":result["pattern_count"],
        "aggregate_rows":len(result["rows"]),
        "symbols_scanned":result["symbols_scanned"],
        "stored":args.write_db,"coverage":result["source_coverage"]},
        ensure_ascii=False))
if __name__=="__main__":main()
