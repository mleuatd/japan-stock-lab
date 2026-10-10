-- Private derived daily research snapshot; NOT broker orders, no licensed OHLCV.
CREATE TABLE IF NOT EXISTS risk_veto_scan_run (
 as_of date PRIMARY KEY,
 scan_state text NOT NULL,
 rule_count integer NOT NULL CHECK (rule_count>=0),
 screened_count integer NOT NULL CHECK (screened_count>=0),
 watch_count integer NOT NULL CHECK (watch_count>=0),
 ready_to_buy integer NOT NULL DEFAULT 0 CHECK (ready_to_buy=0),
 market_status_audit text NOT NULL,
 corporate_action_audit text NOT NULL,
 scanned_at timestamptz NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS risk_veto_symbol_scan (
 as_of date NOT NULL REFERENCES risk_veto_scan_run(as_of),
 security_code text NOT NULL,
 status text NOT NULL,
 matched_veto text[] NOT NULL,
 observed_patterns text[] NOT NULL,
 approval text NOT NULL DEFAULT 'NOT_APPROVED'
    CHECK (approval='NOT_APPROVED'),
 PRIMARY KEY(as_of,security_code)
);
CREATE INDEX IF NOT EXISTS risk_veto_symbol_scan_candidates
 ON risk_veto_symbol_scan (as_of,status);
CREATE OR REPLACE VIEW risk_veto_latest_watch AS
SELECT x.as_of,x.security_code,x.status,x.matched_veto,
       x.approval,r.scan_state,r.market_status_audit,r.corporate_action_audit
FROM risk_veto_symbol_scan x
JOIN risk_veto_scan_run r USING(as_of)
WHERE x.as_of=(SELECT MAX(as_of) FROM risk_veto_scan_run)
  AND x.status='NO_VETO_MATCH_RESEARCH_ONLY'
  AND r.scan_state='RESEARCH_WATCHLIST_ONLY'
ORDER BY x.security_code;
