#!/usr/bin/env python3
"""Research-only: price-pattern -> forward sessions 1..30 descriptive outcomes.

Point-in-time features at signal CLOSE. No future observations in features.
Market-session index (NOT calendar days, not per-symbol observation index).
Aggregate-only storage; no duplicate/private OHLCV or symbol-level evidence.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date

from jpx_market_risk import risk_as_of_close

VERSION="price-patterns-v1"
HORIZONS=tuple(range(1,31))
COOLDOWN=30
DEFINITIONS={
 "BASE":("全銘柄の比較基準","売買のある日足・直前20営業日が揃った基準群"),
 "UP3":("3営業日連続上昇","終値が3営業日連続で上昇"),
 "DOWN3":("3営業日連続下落","終値が3営業日連続で下落"),
 "UP5":("5営業日連続上昇","終値が5営業日連続で上昇"),
 "DOWN5":("5営業日連続下落","終値が5営業日連続で下落"),
 "GAIN5":("5営業日で5%以上上昇","5営業日前からの調整後終値リターンが5%以上"),
 "LOSS5":("5営業日で5%以上下落","5営業日前からの調整後終値リターンが-5%以下"),
 "DIP_REV":("下落後の反発","5営業日で-3%以下、当日は上昇"),
 "RALLY_DIP":("上昇後の反落","5営業日で+3%以上、当日は下落"),
 "HIGH20":("20日高値更新","過去20営業日の高値終値を本日上抜け"),
 "LOW20":("20日安値更新","過去20営業日の安値終値を本日下抜け"),
 "SMA_BULL":("短期平均が長期平均より上","5日平均が20日平均を上回る"),
 "SMA_BEAR":("短期平均が長期平均より下","5日平均が20日平均を下回る"),
 "SIDEWAYS":("20日間の横ばい","20日間の最高終値÷最低終値が1.06以下"),
 "VOL_UP":("出来高急増＋上昇","出来高が過去5日平均の2倍以上かつ当日上昇"),
 "VOL_DOWN":("出来高急増＋下落","出来高が過去5日平均の2倍以上かつ当日下落"),
}

def detect(prices,volumes):
    """Current + previous 20 consecutive *global market* sessions only."""
    if len(prices)!=21 or len(volumes)!=21:
        raise ValueError("Need exactly 21 consecutive daily observations")
    if any(not math.isfinite(x) or x<=0 for x in prices):
        return ()
    if any(not math.isfinite(v) or v<0 for v in volumes) or volumes[-1]<=0:
        return ()
    p=prices;v=volumes
    day=p[-1]/p[-2]-1
    r5=p[-1]/p[-6]-1
    p5=p[-6:]
    last20=p[-20:]
    mean5=sum(p[-5:])/5;mean20=sum(last20)/20
    v5=sum(v[-6:-1])/5
    out=["BASE"]
    if all(p[-j]>p[-j-1] for j in range(1,4)):out.append("UP3")
    if all(p[-j]<p[-j-1] for j in range(1,4)):out.append("DOWN3")
    if all(p[-j]>p[-j-1] for j in range(1,6)):out.append("UP5")
    if all(p[-j]<p[-j-1] for j in range(1,6)):out.append("DOWN5")
    if r5>=.05:out.append("GAIN5")
    if r5<=-.05:out.append("LOSS5")
    if r5<=-.03 and day>0:out.append("DIP_REV")
    if r5>=.03 and day<0:out.append("RALLY_DIP")
    if p[-1]>max(p[-21:-1]):out.append("HIGH20")
    if p[-1]<min(p[-21:-1]):out.append("LOW20")
    if mean5>mean20:out.append("SMA_BULL")
    if mean5<mean20:out.append("SMA_BEAR")
    if max(last20)/min(last20)<=1.06:out.append("SIDEWAYS")
    if v5>0 and v[-1]>=2*v5 and day>0:out.append("VOL_UP")
    if v5>0 and v[-1]>=2*v5 and day<0:out.append("VOL_DOWN")
    return tuple(out)

def wilson(up,n):
    if not n:return (None,None)
    z=1.96
    p=up/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    delta=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (round(max(0,(center-delta)/den)*100,3),
            round(min(1,(center+delta)/den)*100,3))

def new_counter():
    return {"observed":0,"up":0,"down":0,"flat":0,"missing":0,
            "unmatured":0,"return_sum":0.0,"return_sumsq":0.0}

def update_symbol(code,observations,market_days,train_end,holdout_start,totals,
                  cooldown=COOLDOWN):
    """Observations: (global market index, adjusted_close|None, volume|None).

    One symbol retained in memory, streamed in security/date order by Neon.
    No assumptions about future listing membership or future quote availability.
    """
    by_day={i:(float(px) if px is not None else None,
               float(vol) if vol is not None else None)
            for i,px,vol in observations}
    if not by_day:return 0
    last_signal={}
    events=0
    for anchor in sorted(by_day):
        if anchor<20:continue
        signal_day=market_days[anchor]
        if not (signal_day<=train_end or signal_day>=holdout_start):continue
        if risk_as_of_close(code,signal_day):continue  # only verified subset
        span=[by_day.get(i) for i in range(anchor-20,anchor+1)]
        if any(z is None or z[0] is None or z[1] is None for z in span):continue
        tags=detect([z[0] for z in span],[z[1] for z in span])
        if not tags:continue
        segment="train" if signal_day<=train_end else "holdout"
        anchor_price=by_day[anchor][0]
        for tag in tags:
            # Same stock & same pattern may not contribute overlapping outcomes.
            if anchor-last_signal.get((segment,tag),-99999)<cooldown:continue
            last_signal[(segment,tag)]=anchor
            events+=1
            for horizon in HORIZONS:
                bucket=totals[(segment,tag,horizon)]
                i=anchor+horizon
                if i>=len(market_days) or (segment=="train" and market_days[i]>train_end):
                    bucket["unmatured"]+=1
                    continue
                future=by_day.get(i)
                if future is None or future[0] is None or future[0]<=0:
                    bucket["missing"]+=1
                    continue
                v=(future[0]/anchor_price-1)*100
                if not math.isfinite(v):
                    bucket["missing"]+=1
                    continue
                bucket["observed"]+=1
                if v>0:bucket["up"]+=1
                elif v<0:bucket["down"]+=1
                else:bucket["flat"]+=1
                bucket["return_sum"]+=v
                bucket["return_sumsq"]+=v*v
    return events

def report(totals,market_days,train_end,holdout_start,source="private_daily_bar"):
    key=hashlib.sha256(
        ("|".join([VERSION,source,market_days[0],market_days[-1],
                    train_end,holdout_start,str(COOLDOWN)])).encode()
    ).hexdigest()[:32]
    rows=[]
    for segment in ("train","holdout"):
        for tag in DEFINITIONS:
            for h in HORIZONS:
                s=totals.get((segment,tag,h),new_counter())
                n=s["observed"]
                up=s["up"];down=s["down"];flat=s["flat"]
                assert up+down+flat==n
                lo,hi=wilson(up,n)
                events=n+s["missing"]+s["unmatured"]
                rows.append({
                    "segment":segment,"pattern_code":tag,"trading_days_after":h,
                    "events":events,"observed":n,"missing":s["missing"],
                    "unmatured":s["unmatured"],"up":up,"down":down,"flat":flat,
                    "up_pct":round(100*up/n,3) if n else None,
                    "down_pct":round(100*down/n,3) if n else None,
                    "avg_return_pct":round(s["return_sum"]/n,5) if n else None,
                    "up_wilson_lower_pct":lo,"up_wilson_upper_pct":hi,
                    "evidence_status":("INSUFFICIENT_SAMPLE" if n<100
                                       else "HISTORICAL_DESCRIPTIVE_UNVERIFIED")
                })
    return {"version":VERSION,"run_key":key,"source_last_date":market_days[-1],
            "source_first_date":market_days[0],
            "train_end":train_end,"holdout_start":holdout_start,
            "cooldown_sessions":COOLDOWN,
            "source":source,"validation_status":"PROVISIONAL_CORPORATE_ACTIONS_UNVERIFIED",
            "market_status_coverage":"PARTIAL_VERIFIED_JPX_SUBSET",
            "patterns":[{"code":k,"name":v[0],"definition":v[1]}
                        for k,v in DEFINITIONS.items()],
            "stats":rows}

def analyze(data,train_end="2026-01-30",holdout_start="2026-02-02"):
    """Unit-test/local-archive entrypoint: data[day][code] contains Bar."""
    days=sorted(data)
    if not days or train_end>=holdout_start:
        raise ValueError("Invalid training/holdout boundaries")
    by_code=defaultdict(list)
    for i,day in enumerate(days):
        for code,b in data[day].items():
            price=getattr(b,"adj_close",None)
            volume=getattr(b,"volume",None)
            by_code[code].append((i,price,volume))
    stats=defaultdict(new_counter)
    events=sum(update_symbol(code,obs,days,train_end,holdout_start,stats)
               for code,obs in by_code.items())
    result=report(stats,days,train_end,holdout_start)
    result["signal_events"]=events
    return result

def stream_neon(conn,train_end,holdout_start):
    """Use one indexed sequential scan, bounded memory per stock."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT trading_date FROM daily_bar ORDER BY trading_date")
        days=[d[0].isoformat() for d in cur.fetchall()]
    date_idx={day:i for i,day in enumerate(days)}
    totals=defaultdict(new_counter)
    events=0;symbols=0
    # No raw rows output to logs. Server cursor batches stream source data.
    with conn.cursor(name="pattern_forward_stream") as cur:
        cur.itersize=10000
        cur.execute("""SELECT security_code,trading_date,adjusted_close,volume
                       FROM daily_bar ORDER BY security_code,trading_date""")
        current=None;one=[]
        for code,day,adjusted,volume in cur:
            if current is not None and code!=current:
                events+=update_symbol(current,one,days,train_end,holdout_start,totals)
                symbols+=1
                one=[]
            current=code
            price=float(adjusted) if adjusted is not None else None
            vol=float(volume) if volume is not None else None
            one.append((date_idx[day.isoformat()],price,vol))
        if current is not None:
            events+=update_symbol(current,one,days,train_end,holdout_start,totals)
            symbols+=1
    result=report(totals,days,train_end,holdout_start)
    result["signal_events"]=events
    result["scanned_symbols"]=symbols
    return result

def store(conn,result):
    """Atomic replace by deterministic run key, no individual stock history."""
    with conn.transaction():
        with conn.cursor() as cur:
            from pathlib import Path
            schema=Path("sql/007_pattern_forward_outcomes.sql").read_text(encoding="utf8")
            for stmt in schema.split(";"):
                if stmt.strip():cur.execute(stmt)
            cur.execute("""INSERT INTO pattern_study_run
               (run_key,model_version,source_first_date,source_last_date,
                train_end,holdout_start,signal_events,validation_status,market_status_coverage)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (run_key) DO UPDATE SET
                signal_events=EXCLUDED.signal_events,
                validation_status=EXCLUDED.validation_status,
                market_status_coverage=EXCLUDED.market_status_coverage,
                calculated_at=NOW()""",
                (result["run_key"],result["version"],result["source_first_date"],
                 result["source_last_date"],result["train_end"],result["holdout_start"],
                 result["signal_events"],result["validation_status"],
                 result["market_status_coverage"]))
            cur.executemany("""INSERT INTO pattern_definition
                (pattern_code,model_version,pattern_name,definition)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (pattern_code,model_version) DO UPDATE
                SET pattern_name=EXCLUDED.pattern_name,definition=EXCLUDED.definition""",
                [(p["code"],result["version"],p["name"],p["definition"])
                 for p in result["patterns"]])
            cur.execute("DELETE FROM pattern_forward_stat WHERE run_key=%s",
                        (result["run_key"],))
            cur.executemany("""INSERT INTO pattern_forward_stat
                (run_key,pattern_code,model_version,segment,trading_days_after,
                 signal_events,observed_count,missing_count,unmatured_count,
                 up_count,down_count,flat_count,up_pct,down_pct,
                 avg_return_pct,up_wilson_lower_pct,up_wilson_upper_pct,evidence_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(result["run_key"],r["pattern_code"],result["version"],r["segment"],
                  r["trading_days_after"],r["events"],r["observed"],r["missing"],
                  r["unmatured"],r["up"],r["down"],r["flat"],r["up_pct"],
                  r["down_pct"],r["avg_return_pct"],r["up_wilson_lower_pct"],
                  r["up_wilson_upper_pct"],r["evidence_status"])
                 for r in result["stats"]])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--from-neon",action="store_true")
    parser.add_argument("--root",default="archive/daily")
    parser.add_argument("--train-end",default="2026-01-30")
    parser.add_argument("--holdout-start",default="2026-02-02")
    parser.add_argument("--write-db",action="store_true")
    parser.add_argument("--out",help="Optional PRIVATE aggregate JSON file")
    args=parser.parse_args()
    if args.train_end>=args.holdout_start:
        raise SystemExit("Invalid date splits")
    if args.write_db and not args.from_neon:
        raise SystemExit("DB write requires --from-neon")
    if args.from_neon:
        import os
        import psycopg
        url=os.environ.get("DATABASE_URL")
        if not url:raise SystemExit("Missing DATABASE_URL")
        with psycopg.connect(url,sslmode="require") as conn:
            result=stream_neon(conn,args.train_end,args.holdout_start)
            if args.write_db:store(conn,result)
    else:
        from walkforward_backtest import load_bars
        result=analyze(load_bars(args.root),args.train_end,args.holdout_start)
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    totals=sum(x["observed"] for x in result["stats"])
    print(json.dumps({"state":result["validation_status"],
        "patterns":len(result["patterns"]),"horizons":len(HORIZONS),
        "aggregated_stat_rows":len(result["stats"]),"observations":totals,
        "market_status_coverage":result["market_status_coverage"],
        "run_key":result["run_key"],"db_written":args.write_db},
        ensure_ascii=False))

if __name__=="__main__":main()
