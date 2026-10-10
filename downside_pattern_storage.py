"""Transactional Neon persistence for downside-pattern V2 aggregates only."""
import hashlib
from pathlib import Path

def store(conn,result):
    key=hashlib.sha256((
        result["version"]+"|"+result["first_day"]+"|"+result["last_day"]+"|"+
        result["train_end"]+"|"+result["holdout_start"]
    ).encode()).hexdigest()[:32]
    with conn.transaction():
        with conn.cursor() as cur:
            schema=Path("sql/008_downside_patterns_v2.sql").read_text(encoding="utf8")
            for statement in schema.split(";"):
                if statement.strip():cur.execute(statement)
            cur.executemany("""
                INSERT INTO downside_pattern_definition_v2
                    (model_version,pattern_code,pattern_family,pattern_name)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(model_version,pattern_code)
                DO UPDATE SET pattern_family=EXCLUDED.pattern_family,
                              pattern_name=EXCLUDED.pattern_name
            """,[(result["version"],p["code"],p["family"],p["name"])
                   for p in result["patterns"]])
            cur.execute("""
                INSERT INTO downside_pattern_run_v2
                 (run_key,model_version,first_day,last_day,train_end,holdout_start,
                  validation_status,source_coverage,symbols_scanned)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(run_key) DO UPDATE SET
                  validation_status=EXCLUDED.validation_status,
                  source_coverage=EXCLUDED.source_coverage,
                  symbols_scanned=EXCLUDED.symbols_scanned,
                  calculated_at=NOW()
            """,(key,result["version"],result["first_day"],result["last_day"],
                 result["train_end"],result["holdout_start"],
                 result["validation_status"],result["source_coverage"],
                 result.get("symbols_scanned",0)))
            cur.executemany("""
                INSERT INTO downside_pattern_stat_v2
                 (run_key,model_version,pattern_code,segment,horizon,
                  unique_symbols,total_count,observed_count,missing_count,
                  unmatured_count,down_count,up_count,flat_count,close_loss3_pct,
                  close_loss5_pct,close_loss10_pct,path_complete_count,
                  path_unknown_count,touch_loss3_pct,touch_loss5_pct,touch_loss10_pct,
                  down_pct,down_ci95_low,down_ci95_high,mean_return_pct,evidence_state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(run_key,pattern_code,segment,horizon)
                DO UPDATE SET
                  unique_symbols=EXCLUDED.unique_symbols,
                  total_count=EXCLUDED.total_count,
                  observed_count=EXCLUDED.observed_count,
                  missing_count=EXCLUDED.missing_count,
                  unmatured_count=EXCLUDED.unmatured_count,
                  down_count=EXCLUDED.down_count,
                  up_count=EXCLUDED.up_count,
                  flat_count=EXCLUDED.flat_count,
                  close_loss3_pct=EXCLUDED.close_loss3_pct,
                  close_loss5_pct=EXCLUDED.close_loss5_pct,
                  close_loss10_pct=EXCLUDED.close_loss10_pct,
                  path_complete_count=EXCLUDED.path_complete_count,
                  path_unknown_count=EXCLUDED.path_unknown_count,
                  touch_loss3_pct=EXCLUDED.touch_loss3_pct,
                  touch_loss5_pct=EXCLUDED.touch_loss5_pct,
                  touch_loss10_pct=EXCLUDED.touch_loss10_pct,
                  down_pct=EXCLUDED.down_pct,
                  down_ci95_low=EXCLUDED.down_ci95_low,
                  down_ci95_high=EXCLUDED.down_ci95_high,
                  mean_return_pct=EXCLUDED.mean_return_pct,
                  evidence_state=EXCLUDED.evidence_state
            """,[
              (key,result["version"],r["pattern"],r["segment"],r["horizon"],
               r["unique_symbols"],r["total"],r["observed"],r["missing"],
               r["unmatured"],r["down"],r["up"],r["flat"],
               r["close_loss3_pct"],r["close_loss5_pct"],r["close_loss10_pct"],
               r["path_complete"],r["path_unknown"],
               r["touch_loss3_pct"],r["touch_loss5_pct"],r["touch_loss10_pct"],
               r["down_pct"],r["down_ci95_low"],r["down_ci95_high"],
               r["mean_return_pct"],r["state"])
              for r in result["rows"]])
    return key
