-- Personal-use views: never expose licensed output on public web services.
CREATE OR REPLACE VIEW daily_change_rank AS
WITH prepared AS (
 SELECT trading_date,security_code,adjusted_close,volume,trading_value,
 LAG(adjusted_close) OVER(PARTITION BY security_code ORDER BY trading_date) AS previous_adjusted_close,
 LAG(trading_date) OVER(PARTITION BY security_code ORDER BY trading_date) AS previous_trading_date
 FROM daily_bar
), changes AS (
 SELECT *, CASE WHEN previous_adjusted_close>0 AND adjusted_close IS NOT NULL THEN
 ROUND((adjusted_close/previous_adjusted_close-1)*100,4) ELSE NULL END AS pct_change
 FROM prepared
), ranks AS (
 SELECT *, ROW_NUMBER() OVER(PARTITION BY trading_date ORDER BY pct_change DESC NULLS LAST,security_code) AS daily_rank
 FROM changes WHERE pct_change IS NOT NULL
)
SELECT * FROM ranks;

CREATE OR REPLACE VIEW daily_top30_streak AS
WITH calendar AS (
 SELECT trading_date, DENSE_RANK() OVER(ORDER BY trading_date) AS day_number FROM (SELECT DISTINCT trading_date FROM daily_bar) days
), topdays AS (
 SELECT d.trading_date,d.security_code,d.pct_change,d.daily_rank,c.day_number
 FROM daily_change_rank d JOIN calendar c USING(trading_date) WHERE d.daily_rank <= 30
), numbered AS (
 SELECT *,day_number - ROW_NUMBER() OVER(PARTITION BY security_code ORDER BY trading_date) AS streak_group FROM topdays
)
SELECT trading_date,security_code,pct_change,daily_rank,
 COUNT(*) OVER(PARTITION BY security_code,streak_group ORDER BY trading_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS consecutive_top30_days
FROM numbered;
