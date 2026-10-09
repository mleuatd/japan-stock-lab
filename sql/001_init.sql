-- Private J-Quants daily prices; do not expose through public endpoints.
CREATE TABLE IF NOT EXISTS daily_bar (
 trading_date date NOT NULL,
 security_code text NOT NULL,
 open_price numeric, high_price numeric, low_price numeric, close_price numeric,
 volume bigint, trading_value numeric, adjusted_close numeric, adjustment_factor numeric,
 PRIMARY KEY (trading_date, security_code)
);
CREATE INDEX IF NOT EXISTS daily_bar_code_date_idx ON daily_bar (security_code, trading_date DESC);
CREATE TABLE IF NOT EXISTS ingest_day (
 trading_date date PRIMARY KEY,
 state text NOT NULL CHECK (state IN ('complete','market_closed','pending','failed')),
 rows_count integer NOT NULL DEFAULT 0 CHECK (rows_count >= 0),
 payload_checksum text,
 source text NOT NULL,
 collected_at timestamptz NOT NULL DEFAULT now(),
 schema_version integer NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS security_master (
 security_code text NOT NULL,
 name text,
 market_segment text,
 effective_from date NOT NULL,
 effective_to date,
 PRIMARY KEY (security_code,effective_from)
);
CREATE TABLE IF NOT EXISTS backtest_run (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 rule_name text NOT NULL,
 initial_cash numeric NOT NULL DEFAULT 3000000,
 created_at timestamptz NOT NULL DEFAULT now(),
 params jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Each new import execution that actually inserts days gets one batch identity.
-- Historical API-fetch times are unknown and must never be backfilled with import times.
CREATE TABLE IF NOT EXISTS ingest_batch (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 source text NOT NULL DEFAULT 'jquants-csv-gzip',
 imported_days integer NOT NULL DEFAULT 0,
 imported_rows bigint NOT NULL DEFAULT 0
);
ALTER TABLE ingest_day ADD COLUMN IF NOT EXISTS batch_id bigint REFERENCES ingest_batch(id);
ALTER TABLE ingest_day ADD COLUMN IF NOT EXISTS source_fetched_at timestamptz;
