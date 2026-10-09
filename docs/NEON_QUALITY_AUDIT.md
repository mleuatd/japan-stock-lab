# Neon stock-data quality audit (read-only)

This file documents independent SQL checks for the private `japan_stock_lab` database. Run them only with an authenticated private Neon connection. Do not publish query rows, individual prices, or credentials.

## Coverage and integrity

```sql
SELECT count(*) AS bars, count(DISTINCT trading_date) AS sessions,
       min(trading_date) AS first_date, max(trading_date) AS last_date,
       count(*) FILTER (WHERE adjusted_close IS NULL) AS missing_adjusted_close
FROM daily_bar;

SELECT count(*) AS mismatched_manifest_days
FROM (
 SELECT i.trading_date
 FROM ingest_day i LEFT JOIN daily_bar b USING (trading_date)
 GROUP BY i.trading_date, i.rows_count
 HAVING count(b.security_code) <> i.rows_count
) mismatches;

SELECT count(*) AS duplicate_bar_keys
FROM (
 SELECT trading_date, security_code
 FROM daily_bar GROUP BY trading_date, security_code HAVING count(*) > 1
) duplicates;
```

## OHLC and missing-price consistency

```sql
SELECT
 count(*) FILTER (WHERE high_price < low_price
   OR high_price < greatest(open_price,close_price)
   OR low_price > least(open_price,close_price)) AS inconsistent_ohlc,
 count(*) FILTER (WHERE adjusted_close IS NULL AND close_price IS NOT NULL) AS adjusted_only_missing,
 count(*) FILTER (WHERE adjusted_close IS NOT NULL AND close_price IS NULL) AS raw_only_missing,
 count(*) FILTER (WHERE adjusted_close IS NULL AND volume IS NULL) AS price_and_volume_missing,
 count(*) FILTER (WHERE adjusted_close IS NULL AND
   (open_price IS NOT NULL OR high_price IS NOT NULL OR low_price IS NOT NULL
    OR trading_value IS NOT NULL)) AS missing_price_inconsistency,
 count(*) FILTER (WHERE adjustment_factor <= 0) AS invalid_adjustment_factor
FROM daily_bar;
```

## Interpret results carefully

* Missing price and volume on the same row does **not** prove the record is a legitimate no-trade row. Verify source semantics, exchange sessions and corporate actions separately.
* An empty `backtest_run` table means no run is persisted **there**; it does not mean backtest code is missing.
* `daily_change_rank` uses the preceding *available security row*, which may be older than the previous market session; check the gap before treating this as a one-day return.
* J-Quants Free market data is delayed. Do not interpret the last stored session as current trading advice.
* These aggregate-only queries do not validate split-adjusted executions, order fills, dividends, taxes, slippage, or lookahead bias.

## Verified live snapshot (2026-10-10 JST)

* 1,914,081 bars over 433 distinct dates, 2024-10-08 to 2026-07-17.
* 86,324 rows have both `adjusted_close` and `volume` NULL.
* Zero manifest-count mismatches, duplicate bar keys, inconsistent OHLC, adjusted/raw-close disagreement, missing-price inconsistency or nonpositive adjustment factors.
* `security_master`, `backtest_run` and `ingest_batch` were empty at this snapshot.
* These observations are time-specific; rerun checks after imports. No raw market rows are included here.
