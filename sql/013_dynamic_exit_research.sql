-- PRIVATE aggregate adaptive exit backtesting, no public OHLCV/trade records.
CREATE TABLE IF NOT EXISTS dynamic_exit_run (
 run_key text PRIMARY KEY,
 source_run_key text NOT NULL REFERENCES downside_pattern_run_v2(run_key),
 source_commit text NOT NULL,
 train_split date NOT NULL,
 train_end date NOT NULL,
 holdout_start date NOT NULL,
 last_source_day date NOT NULL,
 policy_version text NOT NULL,
 policy_count integer NOT NULL CHECK(policy_count>0),
 rule_count integer NOT NULL CHECK(rule_count>=0),
 scanned_symbols integer NOT NULL CHECK(scanned_symbols>=0),
 status text NOT NULL,
 selected_policy text,
 created_at timestamptz NOT NULL DEFAULT NOW(),
 CHECK(train_split<train_end AND train_end<holdout_start AND holdout_start<last_source_day)
);
CREATE TABLE IF NOT EXISTS dynamic_exit_stat (
 run_key text NOT NULL REFERENCES dynamic_exit_run(run_key),
 segment text NOT NULL CHECK(segment IN ('TRAIN_A','TRAIN_B','HOLDOUT')),
 cohort text NOT NULL CHECK(cohort IN ('ALL','EXCLUDED','SURVIVOR')),
 policy text NOT NULL,
 policy_parameters jsonb NOT NULL,
 events bigint NOT NULL CHECK(events>=0),
 observed bigint NOT NULL CHECK(observed>=0),
 unknown bigint NOT NULL CHECK(unknown>=0),
 loss_count bigint NOT NULL CHECK(loss_count>=0),
 positive_count bigint NOT NULL CHECK(positive_count>=0),
 flat_count bigint NOT NULL CHECK(flat_count>=0),
 loss5_count bigint NOT NULL CHECK(loss5_count>=0),
 net_sum_pct double precision NOT NULL,
 paired_count bigint NOT NULL CHECK(paired_count>=0),
 paired_wins bigint NOT NULL CHECK(paired_wins>=0),
 paired_harms bigint NOT NULL CHECK(paired_harms>=0),
 paired_candidate_loss5 bigint NOT NULL CHECK(paired_candidate_loss5>=0),
 paired_baseline_loss5 bigint NOT NULL CHECK(paired_baseline_loss5>=0),
 paired_delta_sum_pct double precision NOT NULL,
 PRIMARY KEY(run_key,segment,cohort,policy),
 CHECK(events=observed+unknown),
 CHECK(observed=loss_count+positive_count+flat_count),
 CHECK(loss5_count<=loss_count),
 CHECK(paired_count<=observed),
 CHECK(paired_wins+paired_harms<=paired_count),
 CHECK(paired_candidate_loss5<=paired_count),
 CHECK(paired_baseline_loss5<=paired_count)
);
CREATE TABLE IF NOT EXISTS dynamic_exit_day (
 run_key text NOT NULL,
 segment text NOT NULL,
 cohort text NOT NULL,
 policy text NOT NULL,
 exit_day integer NOT NULL CHECK(exit_day BETWEEN 2 AND 30),
 exit_count bigint NOT NULL CHECK(exit_count>=0),
 loss_count bigint NOT NULL CHECK(loss_count>=0),
 net_sum_pct double precision NOT NULL,
 PRIMARY KEY(run_key,segment,cohort,policy,exit_day),
 FOREIGN KEY(run_key,segment,cohort,policy)
  REFERENCES dynamic_exit_stat(run_key,segment,cohort,policy),
 CHECK(loss_count<=exit_count)
);
CREATE OR REPLACE VIEW dynamic_exit_30day_comparison AS
SELECT r.run_key,r.source_commit,r.status,r.train_split,r.train_end,
 r.holdout_start,r.last_source_day,r.selected_policy,
 s.segment,s.cohort,s.policy,s.policy_parameters,s.events,s.observed,s.unknown,
 ROUND(100.0*s.loss_count/NULLIF(s.observed,0),3) AS negative_pct,
 ROUND(100.0*s.positive_count/NULLIF(s.observed,0),3) AS positive_pct,
 ROUND(100.0*s.loss5_count/NULLIF(s.observed,0),3) AS loss5_pct,
 ROUND(s.net_sum_pct::numeric/NULLIF(s.observed,0),4) AS mean_net_pct,
 s.paired_count,s.paired_wins,s.paired_harms,
 ROUND(100.0*(s.paired_wins-s.paired_harms)/NULLIF(s.paired_count,0),3)
 AS paired_any_loss_improvement_pp,
 ROUND(s.paired_delta_sum_pct::numeric/NULLIF(s.paired_count,0),4)
 AS paired_mean_net_improvement_pp,
 'NOT_APPROVED'::text AS trading_approval
FROM dynamic_exit_stat s JOIN dynamic_exit_run r USING(run_key);
