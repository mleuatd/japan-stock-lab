-- Downside research V2: separate tables. Existing V1 tables remain untouched.
-- No raw OHLCV duplication and no public trading/private holdings.
CREATE TABLE IF NOT EXISTS downside_pattern_definition_v2 (
  model_version text NOT NULL,
  pattern_code text NOT NULL,
  pattern_family text NOT NULL,
  pattern_name text NOT NULL,
  PRIMARY KEY(model_version,pattern_code)
);
CREATE TABLE IF NOT EXISTS downside_pattern_run_v2 (
  run_key text PRIMARY KEY,
  model_version text NOT NULL,
  first_day date NOT NULL,
  last_day date NOT NULL,
  train_end date NOT NULL,
  holdout_start date NOT NULL,
  validation_status text NOT NULL,
  source_coverage text NOT NULL,
  symbols_scanned bigint NOT NULL CHECK(symbols_scanned>=0),
  calculated_at timestamptz NOT NULL DEFAULT NOW(),
  CHECK(train_end<holdout_start)
);
CREATE TABLE IF NOT EXISTS downside_pattern_stat_v2 (
  run_key text NOT NULL REFERENCES downside_pattern_run_v2(run_key),
  model_version text NOT NULL,
  pattern_code text NOT NULL,
  segment text NOT NULL CHECK(segment IN ('train','holdout')),
  horizon integer NOT NULL CHECK(horizon BETWEEN 1 AND 30),
  unique_symbols integer NOT NULL CHECK(unique_symbols>=0),
  total_count bigint NOT NULL CHECK(total_count>=0),
  observed_count bigint NOT NULL CHECK(observed_count>=0),
  missing_count bigint NOT NULL CHECK(missing_count>=0),
  unmatured_count bigint NOT NULL CHECK(unmatured_count>=0),
  down_count bigint NOT NULL CHECK(down_count>=0),
  up_count bigint NOT NULL CHECK(up_count>=0),
  flat_count bigint NOT NULL CHECK(flat_count>=0),
  close_loss3_pct numeric,
  close_loss5_pct numeric,
  close_loss10_pct numeric,
  path_complete_count bigint NOT NULL CHECK(path_complete_count>=0),
  path_unknown_count bigint NOT NULL CHECK(path_unknown_count>=0),
  touch_loss3_pct numeric,
  touch_loss5_pct numeric,
  touch_loss10_pct numeric,
  down_pct numeric,
  down_ci95_low numeric,
  down_ci95_high numeric,
  mean_return_pct numeric,
  evidence_state text NOT NULL,
  PRIMARY KEY(run_key,pattern_code,segment,horizon),
  FOREIGN KEY(model_version,pattern_code)
    REFERENCES downside_pattern_definition_v2(model_version,pattern_code),
  CHECK (total_count=observed_count+missing_count+unmatured_count),
  CHECK (observed_count=down_count+up_count+flat_count),
  CHECK (observed_count>=path_complete_count+path_unknown_count)
);
CREATE OR REPLACE VIEW downside_pattern_30day AS
SELECT r.run_key,s.segment,s.pattern_code,p.pattern_name,p.pattern_family,
       r.last_day,r.validation_status,r.source_coverage,
  MAX(s.down_pct) FILTER (WHERE s.horizon=1) AS day01,
  MAX(s.down_pct) FILTER (WHERE s.horizon=2) AS day02,
  MAX(s.down_pct) FILTER (WHERE s.horizon=3) AS day03,
  MAX(s.down_pct) FILTER (WHERE s.horizon=4) AS day04,
  MAX(s.down_pct) FILTER (WHERE s.horizon=5) AS day05,
  MAX(s.down_pct) FILTER (WHERE s.horizon=6) AS day06,
  MAX(s.down_pct) FILTER (WHERE s.horizon=7) AS day07,
  MAX(s.down_pct) FILTER (WHERE s.horizon=8) AS day08,
  MAX(s.down_pct) FILTER (WHERE s.horizon=9) AS day09,
  MAX(s.down_pct) FILTER (WHERE s.horizon=10) AS day10,
  MAX(s.down_pct) FILTER (WHERE s.horizon=11) AS day11,
  MAX(s.down_pct) FILTER (WHERE s.horizon=12) AS day12,
  MAX(s.down_pct) FILTER (WHERE s.horizon=13) AS day13,
  MAX(s.down_pct) FILTER (WHERE s.horizon=14) AS day14,
  MAX(s.down_pct) FILTER (WHERE s.horizon=15) AS day15,
  MAX(s.down_pct) FILTER (WHERE s.horizon=16) AS day16,
  MAX(s.down_pct) FILTER (WHERE s.horizon=17) AS day17,
  MAX(s.down_pct) FILTER (WHERE s.horizon=18) AS day18,
  MAX(s.down_pct) FILTER (WHERE s.horizon=19) AS day19,
  MAX(s.down_pct) FILTER (WHERE s.horizon=20) AS day20,
  MAX(s.down_pct) FILTER (WHERE s.horizon=21) AS day21,
  MAX(s.down_pct) FILTER (WHERE s.horizon=22) AS day22,
  MAX(s.down_pct) FILTER (WHERE s.horizon=23) AS day23,
  MAX(s.down_pct) FILTER (WHERE s.horizon=24) AS day24,
  MAX(s.down_pct) FILTER (WHERE s.horizon=25) AS day25,
  MAX(s.down_pct) FILTER (WHERE s.horizon=26) AS day26,
  MAX(s.down_pct) FILTER (WHERE s.horizon=27) AS day27,
  MAX(s.down_pct) FILTER (WHERE s.horizon=28) AS day28,
  MAX(s.down_pct) FILTER (WHERE s.horizon=29) AS day29,
  MAX(s.down_pct) FILTER (WHERE s.horizon=30) AS day30
FROM downside_pattern_stat_v2 s
JOIN downside_pattern_run_v2 r ON r.run_key=s.run_key
JOIN downside_pattern_definition_v2 p ON p.model_version=s.model_version AND p.pattern_code=s.pattern_code
GROUP BY r.run_key,s.segment,s.pattern_code,p.pattern_name,p.pattern_family,
         r.last_day,r.validation_status,r.source_coverage;
