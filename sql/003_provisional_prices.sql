-- A strictly separate, private provisional price feed. No guessed source and no unlicensed data.
-- Rows are keyed by trading date and instrument, independently of J-Quants final bars.
CREATE TABLE IF NOT EXISTS provisional_bar (
  trading_date date NOT NULL,
  security_code text NOT NULL,
  open_price numeric,
  high_price numeric,
  low_price numeric,
  close_price numeric,
  volume bigint,
  source_name text NOT NULL,
  source_uri text,
  fetched_at timestamptz NOT NULL,
  PRIMARY KEY (trading_date, security_code),
  CHECK (open_price IS NULL OR open_price >= 0),
  CHECK (high_price IS NULL OR high_price >= 0),
  CHECK (low_price IS NULL OR low_price >= 0),
  CHECK (close_price IS NULL OR close_price >= 0),
  CHECK (volume IS NULL OR volume >= 0)
);
CREATE INDEX IF NOT EXISTS provisional_bar_code_date_idx
 ON provisional_bar (security_code, trading_date DESC);

-- The trusted J-Quants record always takes priority on the same (date,code).
-- View does not duplicate the authoritative 2-year history on disk.
CREATE OR REPLACE VIEW daily_bar_best_available AS
SELECT trading_date,security_code,open_price,high_price,low_price,close_price,
 volume,trading_value,adjusted_close,adjustment_factor,
 'jquants'::text AS price_source, false AS is_provisional
FROM daily_bar
UNION ALL
SELECT p.trading_date,p.security_code,p.open_price,p.high_price,p.low_price,p.close_price,
 p.volume,NULL::numeric,NULL::numeric,NULL::numeric,
 p.source_name AS price_source,true AS is_provisional
FROM provisional_bar p
WHERE NOT EXISTS (
 SELECT 1 FROM daily_bar j
 WHERE j.trading_date=p.trading_date AND j.security_code=p.security_code
);
