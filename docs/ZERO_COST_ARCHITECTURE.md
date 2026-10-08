# Zero-cost architecture decision (2026-10-08)

## Hard requirements
- Running cost = 0 JPY, no paid upgrade or enabled overages. At quota boundary **stop with an alert**, never silently incur cost.
- All historical J-Quants bar data must remain private, per the J-Quants API private-use terms (https://jpx-jquants.com/). No public JSON/CSV/Parquet, public SQL endpoint or publicly browsable stock-data UI backed by licensed data.
- Ingestion is resumable, idempotent, and captures provenance; once confirmed saved durably, never request the same day again unless explicitly repairing corrupt/changed data.
- Keep collection and storage separate from the public static frontend. Real orders never placed.

## Provider comparison and decision
Official pricing checked October 8, 2026:
- Turso: free 5 GB storage; 500 million rows read and 10 million rows written monthly; no credit card to start (https://turso.tech/pricing). **Preferred primary SQL store**, conditional on account provisioning and measured dataset footprint. Do not enable paid overages.
- Cloudflare R2: 10 GB-month standard storage, 1M writes and 10M reads monthly; an R2 subscription/checkout is required, and beyond-free use is billed (https://developers.cloudflare.com/r2/pricing/ and https://developers.cloudflare.com/r2/get-started/). Suitable optional raw file backup if account/billing control is acceptable; not default under hard zero-charge rule.
- Neon: 1 GB per project on free tier since 2026-10-02 (https://neon.com/blog/neon-free-plan-1-gb-per-project); standard SQL but tight storage.
- Supabase: 500 MB free database plus 1 GB storage; free projects can pause when inactive (https://supabase.com/docs/guides/platform/billing-on-supabase and https://supabase.com/docs/guides/platform/free-project-pausing).
- GitHub private repository: fallback private snapshot store subject to Git repository growth limits and licensing. GitHub Actions caches and artifacts are not durable.
- DuckDB: local ephemeral analytics engine over private data; open-source SQL engine, **not** by itself a persistent cloud host.

## Target data architecture
```
J-Quants API --(GitHub Actions, secret)--> validated day batches
                              |         --> private Turso SQL (staging + transactional ingest)
                              |         --> private compressed immutable snapshot backup (optional)
                              +-- summary metadata (date, code count, checksum, fetch status)
Turso --> authenticated/private query service --> own-use web interface
```
Do not make credentials available to GitHub Pages JavaScript: a browser cannot conceal tokens. The current docs/index.html prototype remains **local file import only**, not a public API. Public GitHub Pages can host code/UI only; private user queries need authentication and backend rights enforcement.

Schema direction (SQLite-compatible, adjust Turso dialect):
- `daily_bar(trading_date TEXT, security_code TEXT, open/high/low/close NUMERIC, volume INTEGER, trading_value NUMERIC, adjusted_close NUMERIC, adjustment_factor NUMERIC, PRIMARY KEY(trading_date,security_code))`.
- `ingest_day(trading_date PRIMARY KEY, state [complete, market_closed, pending, failed], rows_count, payload_checksum, source, collected_at, schema_version)`.
- `security_master(security_code, name, market_segment, effective_from, effective_to)` **as licensed/available**.
- `job_run(run_id,started_at,finished_at,attempted_days,new_days,skipped_days,errors)`.
- Future `backtest_run`, `backtest_order`, `backtest_position` are segregated from actual brokerage orders.

Ingestion contract:
1. Query completed dates from **durable** `ingest_day` first; cache is only acceleration.
2. Request missing valid trading dates in bounded batches at J-Quants published rate limits.
3. Validate schema, distinct (date,code), numeric sanity, daily row counts, and source-reported pagination completion.
4. Insert bars plus `ingest_day` status atomically for each date, with conflict-ignore keys and checksums; retry failed days without duplicating complete days.
5. Monthly backup + routine restore testing, and stop ingestion on quota/size thresholds.
6. Do not mark an API empty response as market holiday without checking trading calendar.
7. No promise that vendor-hosted free tier is permanent. Provide portable SQL/Parquet exports stored privately and recovery instructions.

## Query and UI design
- Human request -> typed, allow-listed filter structure, not AI-generated arbitrary SQL -> SQL parameter binding -> bounded private result set.
- URL query params describe filters only (e.g. `?date=2024-11-28&metric=change&minvol=100000&limit=30`), contain NO API tokens or full datasets; users must be authenticated to retrieve licensed underlying prices.
- Support daily TOP30, historical rankings, weekly trends, repeated TOP30 streaks, sector/market filters, financial/benefit filters and virtual portfolio as separate revisions.
- Screen-reader-friendly controls: descriptive labels, status summaries, sortable tables, semantically structured headings; mobile first.
- Accurate changes must incorporate split-adjustment data and suspended trading; do not imply unadjusted return is an investment-grade performance measure.

## Current status vs future
**Implemented**: public code repository, working J-Quants ingest with GitHub Actions cache/artifact, CSV validation, basic local-browser filter prototype, optional private GitHub archive adapter not yet configured.
**NOT implemented**: Turso account/database; Turso ingestion adapter; private auth/query API; service-side permanent archive; complete two-year backfill; quota alerts; licensed private web query deployment.
No Turso keys should ever be requested through chat or committed. Configure narrow secrets in GitHub Actions only after provider account exists.

## Next work units
1. Test current archive and finish backfill using current temporary cache while preserving data before artifact expiry.
2. Implement Turso ingestion client & migration scripts, offline SQLite integration tests, and dry-run mode without credentials.
3. Provision Turso free database under user ownership, wire secrets, verify idempotency and private access. No credentials in public repository.
4. Establish an independently restorable private backup compatible with zero cost, and monitor all quota usage.
5. Build private query API + authentication before any server-backed hosted UI. Local-import UI is a separate private-use fallback.
