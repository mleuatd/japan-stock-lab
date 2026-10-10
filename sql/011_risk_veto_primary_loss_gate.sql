-- Fail-closed primary objective review for retrospective risk veto union.
-- A reduction in severe crashes does not excuse an increased chance of ANY loss.
-- All verdicts stay research-only and authorize zero brokerage orders.
CREATE OR REPLACE VIEW risk_veto_union_effectiveness_20day AS
SELECT a.run_key, a.sampling, r.signal_start, r.signal_end,
       r.latest_source_day, r.status AS research_status,
       a.observed AS baseline_observed,
       s.observed AS survivor_observed,
       e.observed AS excluded_observed,
       s.loss_count AS survivor_losses,
       round(100.0*a.loss_count/nullif(a.observed,0),3) AS baseline_loss_pct,
       round(100.0*s.loss_count/nullif(s.observed,0),3) AS survivor_loss_pct,
       round(100.0*e.loss_count/nullif(e.observed,0),3) AS excluded_loss_pct,
       round(100.0*(s.loss_count::numeric/nullif(s.observed,0)
                   -a.loss_count::numeric/nullif(a.observed,0)),3)
                   AS survivor_loss_delta_pp,
       round(100.0*a.touch_loss5_count/nullif(a.path_complete_count,0),3)
                   AS baseline_touch5_pct,
       round(100.0*s.touch_loss5_count/nullif(s.path_complete_count,0),3)
                   AS survivor_touch5_pct,
       round(100.0*a.touch_loss10_count/nullif(a.path_complete_count,0),3)
                   AS baseline_touch10_pct,
       round(100.0*s.touch_loss10_count/nullif(s.path_complete_count,0),3)
                   AS survivor_touch10_pct,
       a.missing AS baseline_missing_outcomes,
       s.missing AS survivor_missing_outcomes,
       'NOT_APPROVED'::text AS trading_approval,
       CASE
         WHEN a.observed<200 OR s.observed<200
           THEN 'INSUFFICIENT_EVIDENCE'
         WHEN s.loss_count::numeric/s.observed
                 >= a.loss_count::numeric/a.observed
           THEN 'FAIL_PRIMARY_ANY_LOSS_RATE'
         ELSE 'IMPROVED_HISTORICALLY_NOT_PROSPECTIVELY_VALIDATED'
       END AS primary_objective_result
FROM risk_veto_union_cohort a
JOIN risk_veto_union_run r ON r.run_key=a.run_key
JOIN risk_veto_union_cohort s
   ON s.run_key=a.run_key AND s.sampling=a.sampling
  AND s.horizon=a.horizon AND s.cohort='SURVIVOR'
JOIN risk_veto_union_cohort e
   ON e.run_key=a.run_key AND e.sampling=a.sampling
  AND e.horizon=a.horizon AND e.cohort='EXCLUDED'
WHERE a.cohort='ALL' AND a.horizon=20;
