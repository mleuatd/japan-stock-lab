-- Private aggregated retrospective veto audit
-- Existing market bars and research tables remain unchanged
CREATE TABLE IF NOT EXISTS risk_veto_union_run (
 run_key text PRIMARY KEY,
 source_run_key text NOT NULL REFERENCES downside_pattern_run_v2(run_key),
 commit_sha text NOT NULL,
 signal_start date NOT NULL,
 signal_end date NOT NULL,
 latest_source_day date NOT NULL,
 rule_count integer NOT NULL CHECK(rule_count>=0),
 scanned_symbols integer NOT NULL CHECK(scanned_symbols>=0),
 status text NOT NULL,
 fee_per_side numeric NOT NULL CHECK(fee_per_side>=0),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(signal_start<=signal_end),
 CHECK(signal_end<latest_source_day)
);
CREATE TABLE IF NOT EXISTS risk_veto_union_cohort (
 run_key text NOT NULL REFERENCES risk_veto_union_run(run_key),
 sampling text NOT NULL CHECK(sampling IN ('daily','spaced30')),
 cohort text NOT NULL CHECK(cohort IN ('ALL','EXCLUDED','SURVIVOR')),
 horizon integer NOT NULL CHECK(horizon BETWEEN 1 AND 30),
 total bigint NOT NULL CHECK(total>=0),
 observed bigint NOT NULL CHECK(observed>=0),
 missing bigint NOT NULL CHECK(missing>=0),
 loss_count bigint NOT NULL CHECK(loss_count>=0),
 up_count bigint NOT NULL CHECK(up_count>=0),
 flat_count bigint NOT NULL CHECK(flat_count>=0),
 close_loss3_count bigint NOT NULL CHECK(close_loss3_count>=0),
 close_loss5_count bigint NOT NULL CHECK(close_loss5_count>=0),
 close_loss10_count bigint NOT NULL CHECK(close_loss10_count>=0),
 path_complete_count bigint NOT NULL CHECK(path_complete_count>=0),
 path_unknown_count bigint NOT NULL CHECK(path_unknown_count>=0),
 touch_loss3_count bigint NOT NULL CHECK(touch_loss3_count>=0),
 touch_loss5_count bigint NOT NULL CHECK(touch_loss5_count>=0),
 touch_loss10_count bigint NOT NULL CHECK(touch_loss10_count>=0),
 net_sum_pct double precision NOT NULL,
 PRIMARY KEY(run_key,sampling,cohort,horizon),
 CHECK(total=observed+missing),
 CHECK(observed=loss_count+up_count+flat_count),
 CHECK(observed=path_complete_count+path_unknown_count),
 CHECK(touch_loss10_count<=touch_loss5_count),
 CHECK(touch_loss5_count<=touch_loss3_count),
 CHECK(path_complete_count>=touch_loss3_count)
);
CREATE TABLE IF NOT EXISTS risk_veto_union_rule (
 run_key text NOT NULL REFERENCES risk_veto_union_run(run_key),
 pattern_code text NOT NULL,
 metric text NOT NULL,
 train_pct numeric NOT NULL,
 train_baseline_pct numeric NOT NULL,
 train_count bigint NOT NULL CHECK(train_count>=0),
 matched20_count bigint NOT NULL CHECK(matched20_count>=0),
 observed20_count bigint NOT NULL CHECK(observed20_count>=0),
 loss20_count bigint NOT NULL CHECK(loss20_count>=0),
 PRIMARY KEY(run_key,pattern_code),
 CHECK(matched20_count>=observed20_count),
 CHECK(observed20_count>=loss20_count)
);
CREATE TABLE IF NOT EXISTS risk_veto_union_snapshot (
 run_key text NOT NULL REFERENCES risk_veto_union_run(run_key),
 as_of date NOT NULL,
 security_code text NOT NULL,
 status text NOT NULL,
 matched_veto text[] NOT NULL,
 PRIMARY KEY(run_key,as_of,security_code)
);
CREATE INDEX IF NOT EXISTS risk_veto_union_snapshot_status_idx
 ON risk_veto_union_snapshot (run_key,status);
CREATE OR REPLACE VIEW risk_veto_union_20day AS
SELECT r.run_key,r.signal_start,r.signal_end,r.latest_source_day,
 r.status,c.sampling,c.cohort,c.total,c.observed,c.missing,
 c.loss_count,round(100.0*c.loss_count/nullif(c.observed,0),3) loss_pct,
 c.close_loss5_count,
 round(100.0*c.close_loss5_count/nullif(c.observed,0),3) close_loss5_pct,
 c.path_complete_count,c.touch_loss5_count,
 round(100.0*c.touch_loss5_count/nullif(c.path_complete_count,0),3) touch_loss5_pct,
 round(c.net_sum_pct::numeric/nullif(c.observed,0),3) mean_net_pct
FROM risk_veto_union_cohort c
JOIN risk_veto_union_run r USING(run_key)
WHERE c.horizon=20;
