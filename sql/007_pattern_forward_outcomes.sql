-- Research-only aggregate storage. No OHLCV duplication or personal trade records.
-- Run_key fingerprinted from algorithm version, observed source period and split.
CREATE TABLE IF NOT EXISTS pattern_definition (
  pattern_code text NOT NULL,
  model_version text NOT NULL,
  pattern_name text NOT NULL,
  definition text NOT NULL,
  PRIMARY KEY (pattern_code,model_version)
);
CREATE TABLE IF NOT EXISTS pattern_study_run (
  run_key text PRIMARY KEY,
  model_version text NOT NULL,
  source_first_date date NOT NULL,
  source_last_date date NOT NULL,
  train_end date NOT NULL,
  holdout_start date NOT NULL,
  signal_events bigint NOT NULL CHECK (signal_events>=0),
  validation_status text NOT NULL,
  market_status_coverage text NOT NULL,
  calculated_at timestamptz NOT NULL DEFAULT NOW(),
  CHECK (train_end < holdout_start)
);
CREATE TABLE IF NOT EXISTS pattern_forward_stat (
  run_key text NOT NULL REFERENCES pattern_study_run(run_key),
  pattern_code text NOT NULL,
  model_version text NOT NULL,
  segment text NOT NULL CHECK (segment IN ('train','holdout')),
  trading_days_after integer NOT NULL CHECK (trading_days_after BETWEEN 1 AND 30),
  signal_events bigint NOT NULL CHECK(signal_events>=0),
  observed_count bigint NOT NULL CHECK(observed_count>=0),
  missing_count bigint NOT NULL CHECK(missing_count>=0),
  unmatured_count bigint NOT NULL CHECK(unmatured_count>=0),
  up_count bigint NOT NULL CHECK(up_count>=0),
  down_count bigint NOT NULL CHECK(down_count>=0),
  flat_count bigint NOT NULL CHECK(flat_count>=0),
  up_pct numeric,
  down_pct numeric,
  avg_return_pct numeric,
  up_wilson_lower_pct numeric,
  up_wilson_upper_pct numeric,
  evidence_status text NOT NULL,
  PRIMARY KEY(run_key,pattern_code,segment,trading_days_after),
  FOREIGN KEY (pattern_code,model_version)
    REFERENCES pattern_definition(pattern_code,model_version),
  CHECK (observed_count=up_count+down_count+flat_count),
  CHECK (signal_events=observed_count+missing_count+unmatured_count)
);
-- View: exactly one row per pattern/segment/run, day01..day30 are
-- historically observed upward-fraction percentages, NOT forecast confidence.
CREATE OR REPLACE VIEW pattern_up_30day AS
SELECT r.run_key,r.model_version,r.segment,r.pattern_code,
       p.pattern_name,r.validation_status,r.market_status_coverage,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=1) AS day01,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=2) AS day02,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=3) AS day03,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=4) AS day04,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=5) AS day05,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=6) AS day06,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=7) AS day07,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=8) AS day08,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=9) AS day09,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=10) AS day10,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=11) AS day11,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=12) AS day12,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=13) AS day13,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=14) AS day14,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=15) AS day15,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=16) AS day16,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=17) AS day17,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=18) AS day18,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=19) AS day19,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=20) AS day20,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=21) AS day21,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=22) AS day22,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=23) AS day23,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=24) AS day24,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=25) AS day25,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=26) AS day26,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=27) AS day27,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=28) AS day28,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=29) AS day29,
  MAX(s.up_pct) FILTER (WHERE s.trading_days_after=30) AS day30
FROM pattern_forward_stat s
JOIN pattern_study_run r ON r.run_key=s.run_key
JOIN pattern_definition p ON p.pattern_code=s.pattern_code
 AND p.model_version=s.model_version
GROUP BY r.run_key,r.model_version,r.segment,r.pattern_code,p.pattern_name,
         r.validation_status,r.market_status_coverage
ORDER BY r.run_key,r.segment,r.pattern_code;
