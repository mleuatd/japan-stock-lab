-- J-Quants daily-bar ex-date adjustment factor audit (private Neon only).
-- 0.5 on a 2:1 split ex-date; the prior AdjC/C ratio should equal
-- the current AdjC/C ratio multiplied by today's factor.
-- 0.5% tolerance allows published AdjC rounding for very low-priced shares.
-- No prices or individual issuer audit details go to GitHub.
CREATE OR REPLACE VIEW split_adjustment_integrity_events AS
WITH history AS (
  SELECT security_code,trading_date,adjustment_factor,
         CASE WHEN adjusted_close>0 AND close_price>0
              THEN adjusted_close/close_price END AS ratio,
         LAG(CASE WHEN adjusted_close>0 AND close_price>0
              THEN adjusted_close/close_price END)
         OVER(PARTITION BY security_code ORDER BY trading_date) AS prior_ratio
  FROM daily_bar
), classified AS (
  SELECT security_code,trading_date,adjustment_factor,
    CASE
      WHEN adjustment_factor IS NULL OR adjustment_factor<=0
        THEN 'UNKNOWN_INVALID_FACTOR'
      WHEN adjustment_factor<>1 AND (prior_ratio IS NULL OR ratio IS NULL)
        THEN 'UNKNOWN_NO_SPLIT_BOUNDARY_PRICE'
      WHEN adjustment_factor<>1 AND
        ABS(prior_ratio/ratio/adjustment_factor-1)>0.005
        THEN 'UNKNOWN_FACTOR_ADJPRICE_MISMATCH'
      WHEN adjustment_factor=1 AND prior_ratio>0 AND ratio>0
        AND ABS(prior_ratio/ratio-1)>0.005
        THEN 'UNKNOWN_UNEXPLAINED_ADJPRICE_CHANGE'
      WHEN adjustment_factor<>1 THEN 'VERIFIED_SPLIT_ADJUSTMENT'
    END AS audit_status
  FROM history
)
SELECT security_code,trading_date,adjustment_factor,audit_status
FROM classified WHERE audit_status IS NOT NULL;

CREATE OR REPLACE VIEW split_adjustment_blocklist AS
SELECT security_code,
       COUNT(*) AS unverified_event_count,
       STRING_AGG(DISTINCT audit_status, ', ' ORDER BY audit_status) AS reasons
FROM split_adjustment_integrity_events
WHERE audit_status<>'VERIFIED_SPLIT_ADJUSTMENT'
GROUP BY security_code;

CREATE OR REPLACE VIEW split_adjustment_integrity_summary AS
SELECT COUNT(*) AS adjustment_event_count,
       COUNT(*) FILTER(WHERE audit_status='VERIFIED_SPLIT_ADJUSTMENT')
         AS verified_event_count,
       COUNT(*) FILTER(WHERE audit_status<>'VERIFIED_SPLIT_ADJUSTMENT')
         AS unverified_event_count,
       COUNT(DISTINCT security_code) FILTER(WHERE audit_status='VERIFIED_SPLIT_ADJUSTMENT')
         AS verified_tickers,
       COUNT(DISTINCT security_code) FILTER(WHERE audit_status<>'VERIFIED_SPLIT_ADJUSTMENT')
         AS excluded_tickers
FROM split_adjustment_integrity_events;
