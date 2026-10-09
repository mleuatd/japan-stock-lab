-- Return bucket/range from **adjusted closing prices**, never inferred returns.
-- Exactly one band matches any finite percent change; NULL for missing previous close.
CREATE TABLE IF NOT EXISTS price_change_band (
 band_code text PRIMARY KEY,
 band_name text NOT NULL,
 percent_range numrange NOT NULL,
 sort_order integer NOT NULL UNIQUE,
 polarity text NOT NULL CHECK (polarity IN ('up','flat','down'))
);
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_10_plus','10%以上下落',numrange(NULL,-10,'[)'),1,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_5_10','5～10%下落',numrange(-10,-5,'[)'),2,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_3_5','3～5%下落',numrange(-5,-3,'[)'),3,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_2_3','2～3%下落',numrange(-3,-2,'[)'),4,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_1_2','1～2%下落',numrange(-2,-1,'[)'),5,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_05_1','0.5～1%下落',numrange(-1,-0.5,'[)'),6,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('fall_under_05','0～0.5%下落',numrange(-0.5,0,'[)'),7,'down') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('unchanged','変動なし',numrange(0,0,'[]'),8,'flat') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_under_05','0～0.5%上昇',numrange(0,0.5,'()'),9,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_05_1','0.5～1%上昇',numrange(0.5,1,'[)'),10,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_1_2','1～2%上昇',numrange(1,2,'[)'),11,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_2_3','2～3%上昇',numrange(2,3,'[)'),12,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_3_5','3～5%上昇',numrange(3,5,'[)'),13,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_5_10','5～10%上昇',numrange(5,10,'[)'),14,'up') ON CONFLICT(band_code) DO NOTHING;
INSERT INTO price_change_band(band_code,band_name,percent_range,sort_order,polarity) VALUES ('rise_10_plus','10%以上上昇',numrange(10,NULL,'[)'),15,'up') ON CONFLICT(band_code) DO NOTHING;

-- Monotonic trend run definitions; one row per direction+minimum streak, reusable filter master.
CREATE TABLE IF NOT EXISTS price_streak_rule (
 rule_code text PRIMARY KEY,
 rule_name text NOT NULL,
 direction text NOT NULL CHECK (direction IN ('up','down','flat')),
 min_consecutive_days integer NOT NULL CHECK(min_consecutive_days BETWEEN 1 AND 60),
 min_daily_change_pct numeric NOT NULL DEFAULT 0 CHECK(min_daily_change_pct >= 0),
 enabled boolean NOT NULL DEFAULT true
);
INSERT INTO price_streak_rule(rule_code,rule_name,direction,min_consecutive_days,min_daily_change_pct) VALUES
 ('up_2','2営業日連続上昇','up',2,0),
 ('up_3','3営業日連続上昇','up',3,0),
 ('up_5','5営業日連続上昇','up',5,0),
 ('up_10','10営業日連続上昇','up',10,0),
 ('up_3_over_1','1%以上が3営業日連続','up',3,1),
 ('down_2','2営業日連続下落','down',2,0),
 ('down_3','3営業日連続下落','down',3,0),
 ('down_5','5営業日連続下落','down',5,0),
 ('down_10','10営業日連続下落','down',10,0),
 ('down_3_over_1','1%以上が3営業日連続下落','down',3,1)
ON CONFLICT(rule_code) DO NOTHING;

-- Virtual view: one value per available daily bar; no persistent duplicate OHLCV.
CREATE OR REPLACE VIEW price_daily_movement AS
WITH lagged AS (
 SELECT trading_date,security_code,adjusted_close,
 LAG(adjusted_close) OVER(PARTITION BY security_code ORDER BY trading_date) AS prior_close,
 LAG(trading_date) OVER(PARTITION BY security_code ORDER BY trading_date) AS prior_date
 FROM daily_bar
), scored AS (
 SELECT trading_date,security_code,adjusted_close,prior_close,prior_date,
 CASE WHEN prior_close>0 AND adjusted_close IS NOT NULL
 THEN ROUND((adjusted_close/prior_close-1)*100,6) END AS pct_change
 FROM lagged
)
SELECT s.*,b.band_code,b.band_name,b.polarity
FROM scored s LEFT JOIN price_change_band b ON s.pct_change <@ b.percent_range;

-- Consecutive up/down/unchanged recorded sessions; NULL/missing closes break a streak.
CREATE OR REPLACE VIEW price_daily_streak AS
WITH movements AS (
 SELECT m.*,CASE WHEN pct_change>0 THEN 'up'
 WHEN pct_change<0 THEN 'down'
 WHEN pct_change=0 THEN 'flat' ELSE 'unknown' END AS direction
 FROM price_daily_movement m
), flags AS (
 SELECT movements.*,
 CASE WHEN direction='unknown'
   OR LAG(direction) OVER (PARTITION BY security_code ORDER BY trading_date) IS DISTINCT FROM direction
   THEN 1 ELSE 0 END AS starts_new_group
 FROM movements
), islands AS (
 SELECT flags.*,
 SUM(starts_new_group) OVER (PARTITION BY security_code ORDER BY trading_date ROWS UNBOUNDED PRECEDING) AS grp
 FROM flags
)
SELECT trading_date,security_code,adjusted_close,prior_close,prior_date,pct_change,
 band_code,band_name,polarity,direction,
 CASE WHEN direction='unknown' THEN 0
 ELSE ROW_NUMBER() OVER (PARTITION BY security_code,grp ORDER BY trading_date) END AS consecutive_days
FROM islands;
