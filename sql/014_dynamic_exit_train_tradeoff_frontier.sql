-- Non-destructive PRIVATE reporting: 2D loss-rate versus net-return frontier.
-- Calculate entirely from frozen TRAIN_A and TRAIN_B paired-event summaries.
-- HOLDOUT must NOT influence classification or Pareto membership.
CREATE OR REPLACE VIEW dynamic_exit_train_tradeoff_frontier AS
WITH fold AS (
  SELECT run_key,policy,segment,paired_count,
         100.0::numeric*(paired_wins-paired_harms)/NULLIF(paired_count,0)
           AS avoided_any_loss_delta_pp,
         paired_delta_sum_pct::numeric/NULLIF(paired_count,0)
           AS mean_net_delta_pp,
         100.0::numeric*(paired_baseline_loss5-paired_candidate_loss5)
           /NULLIF(paired_count,0) AS avoided_loss5_delta_pp,
         100.0::numeric*unknown/NULLIF(events,0) AS unknown_pct
    FROM dynamic_exit_stat
   WHERE cohort='SURVIVOR' AND segment IN ('TRAIN_A','TRAIN_B')
), grouped AS (
 SELECT run_key,policy,
        COUNT(*) AS fold_count,MIN(paired_count) AS min_paired_count,
        MIN(avoided_any_loss_delta_pp) AS min_avoided_any_loss_delta_pp,
        MAX(avoided_any_loss_delta_pp) AS max_avoided_any_loss_delta_pp,
        MIN(mean_net_delta_pp) AS min_mean_net_delta_pp,
        MAX(mean_net_delta_pp) AS max_mean_net_delta_pp,
        MIN(avoided_loss5_delta_pp) AS min_avoided_loss5_delta_pp,
        MAX(unknown_pct) AS max_unknown_pct
 FROM fold GROUP BY run_key,policy
), eligible AS (
 SELECT * FROM grouped WHERE fold_count=2
)
SELECT p.run_key,p.policy,p.min_paired_count,
 ROUND(p.min_avoided_any_loss_delta_pp,3) AS worst_train_loss_prevention_pp,
 ROUND(p.max_avoided_any_loss_delta_pp,3) AS best_train_loss_prevention_pp,
 ROUND(p.min_mean_net_delta_pp,4) AS worst_train_mean_return_gain_pp,
 ROUND(p.max_mean_net_delta_pp,4) AS best_train_mean_return_gain_pp,
 ROUND(p.min_avoided_loss5_delta_pp,3) AS worst_train_severe5_prevention_pp,
 ROUND(p.max_unknown_pct,3) AS worst_train_unknown_pct,
 CASE WHEN p.min_avoided_any_loss_delta_pp>0 AND p.min_mean_net_delta_pp>=0
              AND p.min_avoided_loss5_delta_pp>=0
     THEN 'DUAL_GAIN_DESCRIPTIVE'
      WHEN p.min_avoided_any_loss_delta_pp>0 AND p.min_mean_net_delta_pp<0
     THEN 'LOSS_PREVENTION_WITH_RETURN_COST'
      WHEN p.min_avoided_any_loss_delta_pp<0 AND p.min_mean_net_delta_pp>0
     THEN 'RETURN_GAIN_WITH_MORE_LOSSES'
      ELSE 'MIXED_OR_NO_GAIN' END AS tradeoff_kind,
 NOT EXISTS (
  SELECT 1 FROM eligible better
   WHERE better.run_key=p.run_key AND better.policy<>p.policy
    AND better.min_avoided_any_loss_delta_pp>=p.min_avoided_any_loss_delta_pp
    AND better.min_mean_net_delta_pp>=p.min_mean_net_delta_pp
    AND (better.min_avoided_any_loss_delta_pp>p.min_avoided_any_loss_delta_pp
      OR better.min_mean_net_delta_pp>p.min_mean_net_delta_pp)
 ) AS on_two_objective_frontier,
 'TRAIN_DESCRIPTIVE_NOT_VALIDATED'::text AS evaluation_state,
 'NOT_APPROVED'::text AS trading_approval
 FROM eligible p;
