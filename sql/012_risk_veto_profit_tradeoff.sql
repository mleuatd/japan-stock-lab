-- Private retrospective upside / downside tradeoff from stored cohort aggregates.
-- No read or duplication of J-Quants raw daily OHLCV.
CREATE OR REPLACE VIEW risk_veto_union_profit_tradeoff AS
SELECT r.run_key,r.signal_start,r.signal_end,r.latest_source_day,
       r.status AS research_status,c.sampling,c.horizon,c.cohort,
       c.total,c.observed,c.missing,c.up_count,c.loss_count,c.flat_count,
       ROUND(100.0*c.up_count/NULLIF(c.observed,0),3) AS positive_pct,
       ROUND(100.0*c.loss_count/NULLIF(c.observed,0),3) AS negative_pct,
       ROUND(100.0*c.flat_count/NULLIF(c.observed,0),3) AS flat_pct,
       ROUND(c.net_sum_pct::numeric/NULLIF(c.observed,0),3) AS mean_net_pct,
       ROUND(100.0*c.close_loss5_count/NULLIF(c.observed,0),3) AS close_loss5_pct,
       ROUND(100.0*c.touch_loss5_count/NULLIF(c.path_complete_count,0),3) AS touch_loss5_pct,
       ROUND(100.0*c.touch_loss10_count/NULLIF(c.path_complete_count,0),3) AS touch_loss10_pct,
       ROUND(100.0*b.up_count/NULLIF(b.observed,0),3) AS baseline_positive_pct,
       ROUND(100.0*b.loss_count/NULLIF(b.observed,0),3) AS baseline_negative_pct,
       ROUND(100.0*(c.up_count::numeric/NULLIF(c.observed,0)
               -b.up_count::numeric/NULLIF(b.observed,0)),3) AS positive_delta_pp,
       ROUND(100.0*(c.loss_count::numeric/NULLIF(c.observed,0)
               -b.loss_count::numeric/NULLIF(b.observed,0)),3) AS negative_delta_pp,
       ROUND(c.net_sum_pct::numeric/NULLIF(c.observed,0)
               -b.net_sum_pct::numeric/NULLIF(b.observed,0),3) AS mean_net_delta_pp,
       'NOT_APPROVED'::text AS trading_approval
FROM risk_veto_union_cohort c
JOIN risk_veto_union_run r USING(run_key)
JOIN risk_veto_union_cohort b
  ON b.run_key=c.run_key AND b.sampling=c.sampling
 AND b.horizon=c.horizon AND b.cohort='ALL';
