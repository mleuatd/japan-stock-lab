CREATE TABLE IF NOT EXISTS conditional_exit_run (
 run_key text PRIMARY KEY,
 source_run text NOT NULL REFERENCES downside_pattern_run_v2(run_key),
 commit_sha text NOT NULL,
 version text NOT NULL,
 train_split date NOT NULL,
 train_end date NOT NULL,
 holdout_start date NOT NULL,
 source_through date NOT NULL,
 scanned_symbols integer NOT NULL CHECK(scanned_symbols>=0),
 decision jsonb NOT NULL,
 status text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(train_split<train_end AND train_end<holdout_start)
);
CREATE TABLE IF NOT EXISTS conditional_exit_effect (
 run_key text NOT NULL REFERENCES conditional_exit_run(run_key),
 segment text NOT NULL CHECK(segment IN ('TRAIN_A','TRAIN_B','HOLDOUT')),
 cohort text NOT NULL CHECK(cohort IN ('ALL','SURVIVOR')),
 rule text NOT NULL,
 explanation text NOT NULL,
 episodes bigint NOT NULL CHECK(episodes>=0),
 exit_count bigint NOT NULL CHECK(exit_count>=0),
 prevented bigint NOT NULL CHECK(prevented>=0),
 introduced bigint NOT NULL CHECK(introduced>=0),
 baseline_loss bigint NOT NULL CHECK(baseline_loss>=0),
 policy_loss bigint NOT NULL CHECK(policy_loss>=0),
 baseline_severe bigint NOT NULL CHECK(baseline_severe>=0),
 policy_severe bigint NOT NULL CHECK(policy_severe>=0),
 baseline_net_sum double precision NOT NULL,
 policy_net_sum double precision NOT NULL,
 PRIMARY KEY (run_key,segment,cohort,rule),
 CHECK(exit_count<=episodes AND prevented+introduced<=episodes),
 CHECK(baseline_loss<=episodes AND policy_loss<=episodes)
);
CREATE TABLE IF NOT EXISTS conditional_exit_day (
 run_key text NOT NULL REFERENCES conditional_exit_run(run_key),
 segment text NOT NULL CHECK(segment IN ('TRAIN_A','TRAIN_B','HOLDOUT')),
 cohort text NOT NULL CHECK(cohort IN ('ALL','SURVIVOR')),
 held_day integer NOT NULL CHECK(held_day BETWEEN 1 AND 28),
 feature text NOT NULL,
 observations bigint NOT NULL CHECK(observations>=0),
 hold_loss bigint NOT NULL CHECK(hold_loss>=0),
 next_open_loss bigint NOT NULL CHECK(next_open_loss>=0),
 prevented bigint NOT NULL CHECK(prevented>=0),
 introduced bigint NOT NULL CHECK(introduced>=0),
 hold_net_sum double precision NOT NULL,
 next_open_net_sum double precision NOT NULL,
 PRIMARY KEY (run_key,segment,cohort,held_day,feature),
 CHECK(hold_loss<=observations AND next_open_loss<=observations)
);
CREATE OR REPLACE VIEW conditional_exit_reasoned_effect AS
SELECT r.run_key,r.created_at,r.source_through,r.decision->>'selected' AS train_a_selected_rule,
 r.decision->>'state' AS replication_state,
 e.segment,e.cohort,e.rule,e.explanation,e.episodes,e.exit_count,
 ROUND(100.0*e.baseline_loss/NULLIF(e.episodes,0),3) AS hold30_loss_pct,
 ROUND(100.0*e.policy_loss/NULLIF(e.episodes,0),3) AS rule_loss_pct,
 e.prevented,e.introduced,
 ROUND(100.0*(e.prevented-e.introduced)/NULLIF(e.episodes,0),3)
   AS avoided_any_loss_pp,
 ROUND(100.0*(e.baseline_severe-e.policy_severe)/NULLIF(e.episodes,0),3)
   AS avoided_loss5_pp,
 ROUND((e.policy_net_sum-e.baseline_net_sum)::numeric/NULLIF(e.episodes,0),4)
   AS mean_net_delta_pp,
 'NOT_APPROVED'::text AS trading_approval
FROM conditional_exit_effect e JOIN conditional_exit_run r USING(run_key);
CREATE OR REPLACE VIEW conditional_exit_daily_causes AS
SELECT r.run_key,r.source_through,d.segment,d.cohort,d.held_day,
 d.feature,d.observations,
 ROUND(100.0*d.hold_loss/NULLIF(d.observations,0),3) AS state_hold30_loss_pct,
 ROUND(100.0*d.next_open_loss/NULLIF(d.observations,0),3) AS state_next_open_sell_loss_pct,
 d.prevented,d.introduced,
 ROUND(100.0*(d.prevented-d.introduced)/NULLIF(d.observations,0),3)
   AS state_avoided_loss_pp,
 ROUND((d.next_open_net_sum-d.hold_net_sum)::numeric/NULLIF(d.observations,0),4)
   AS state_mean_net_delta_pp
FROM conditional_exit_day d JOIN conditional_exit_run r USING(run_key);
