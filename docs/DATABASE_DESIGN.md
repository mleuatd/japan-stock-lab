# Neon PostgreSQL search/storage strategy (2026-10-09)

## Decision: one `daily_bar` table, no yearly split

Current live measured database contains 766,639 daily bars across 174 sessions and 4,504 distinct codes (2024-10-08 through 2025-06-25). Keep the existing single `daily_bar` table and existing two B-tree indexes; do **not** create yearly tables or partition the table unless reproducible benchmark evidence warrants a change. Existing uniqueness is enforced by primary key `(trading_date,security_code)`.

Existing indexes:
- `daily_bar_pkey (trading_date, security_code)`: date/snapshot queries and uniqueness
- `daily_bar_code_date_idx (security_code, trading_date DESC)`: symbol history/range queries

Live `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` sample measurements (warm/cold cache may vary):
- symbol `54230`, Jan 1–June 25 2025, 116 returned rows: ~6.272 ms server execution
- June 25 2025, sort close descending and LIMIT 30: ~1.993 ms server execution
- June 25 2025 all codes ordered by code, 4,408 rows: ~12.053 ms server execution

Space metrics at measurement:
- `daily_bar` total `pg_total_relation_size` approximately 122 MB.
- The `daily_bar` heap approximately 67 MB; its two B-tree indexes together approximately 55 MB (primary ~23 MB, code/date ~32 MB).
- Entire PostgreSQL database `pg_database_size` = 135,692,288 bytes (~135.7 MB decimal), including other objects.
- PostgreSQL internal metrics are not necessarily the same as Neon platform billed logical storage, compute, transfer or retention. Monitor both.

## Why do not split by calendar year now?

- A filter across multiple years would need to search several yearly tables or a UNION/view. Inserts and schema migrations become harder.
- PostgreSQL declarative RANGE partitioning on `trading_date` could present a single logical table, but partitions add per-partition metadata and indexes and complicate uniqueness/migrations. For an expected ~500 trading days (~2 million rows) and these demonstrated query latencies, partitioning is premature.
- Data volume is **not** doubled by reading it or by a SQL view. A materialized view or an additional index **does** consume disk; ordinary views do not store a second copy of bars.
- If search patterns, performance or storage change, re-measure before changing schema. Retain a safe rollback path and complete backup before any partitioning migration.

## Query conventions

```sql
-- History for one instrument, indexed by (security_code, trading_date DESC)
SELECT trading_date, open_price, high_price, low_price, close_price, volume
FROM daily_bar
WHERE security_code = $1
  AND trading_date >= $2
  AND trading_date < $3
ORDER BY trading_date;

-- Full snapshot for one date, indexed by primary key
SELECT security_code, open_price, high_price, low_price, close_price, volume
FROM daily_bar WHERE trading_date = $1
ORDER BY security_code;

-- Predefined rankings currently exist as normal, non-materialized views.
SELECT * FROM daily_change_rank WHERE trading_date = $1 AND daily_rank <= 30;
```

Parameter placeholders above are illustrative PostgreSQL prepared-statement parameters; Python psycopg should continue to bind values with `%s`.

## Optimization policy

1. Measure representative production SQL with `EXPLAIN (ANALYZE, BUFFERS)`, actual result cardinality and cold/warm caches.
2. Prefer existing composite indexes and date-range predicates to new permanent indexes. Avoid `SELECT *` for client-facing APIs and paginate large result sets.
3. Only add an index once a real frequent/slow query is identified. Benchmark speedup **and** storage delta, and keep record of the query. Existing indexes already use ~55 MB.
4. Views are suitable for rankings initially. Do not materialize full OHLCV copies to precompute indicators. Use query-time computation or narrow aggregate tables only if repeated measurements justify them.
5. Avoid raw licensed J-Quants exports on public GitHub or unauthenticated Pages; design an authenticated, license-compliant data API before exposing private prices.
6. For Neon Free, preserve safety stop before new imports when `pg_database_size` is >=700,000,000 bytes; also observe platform limits and CU-hours. Read queries consume compute too.
7. If the table approaches millions of rows and frequent range queries regress significantly, examine BRIN for date-ordered append workloads, narrower covering indexes, updated statistics, and RANGE partitioning *only after real comparative measurement*.

## Future query classes / schema boundaries

- OHLCV remains in `daily_bar`; no per-year clones and no redundant archive table.
- Security identifiers/names/markets in `security_master`, updated separately.
- Separate small normalized tables for corporate actions, dividends, shareholder benefits, market calendar, strategies, trades and backtest results only as needed. Do not repeat descriptive attributes in every price row.
- Favor joins on instrument/date keys and candidate screening indexes based on observed query plans; add constraints and stable keys to maintain data consistency.

## Operations and validation

- Existing importer processes each trading day atomically, uses `ON CONFLICT DO NOTHING`, verifies row counts and marks `ingest_day` complete, and skips already complete days.
- Do not delete or rewrite existing bars as a performance experiment.
- For any migration use safe Neon preview/test branches and explicit review before production DDL. Any destructive action requires user confirmation.
- Keep archive in durable **private** backup outside public repository; current GitHub Actions cache/artifacts are temporary.
