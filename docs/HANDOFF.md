# Collection handoff — 2026-10-08 JST

Repository: mleuatd/japan-stock-lab (main). Do not modify mleuatd/dtx-drum-flow.

## Verified initial run

- Run #1: https://github.com/mleuatd/japan-stock-lab/actions/runs/37769040642
- GitHub status: completed / success, run ID 37769040642; all job steps passed.
- JQUANTS_API_KEY was present; API responses returned actual daily bars.
- 20 weekday requests spanning 2024-10-08 through 2024-11-04; 18 saved days, 2 NO_DATA dates (2024-10-14 and 2024-11-04 Japanese exchange holidays).
- Archive artifact ID 11546803389, name `daily-bars-37769040642`, approximately 1.6 MB, expires **2026-11-07 20:23 JST**. GitHub caches/artifacts are not permanent.
- Downloaded and inspected ZIP: 18 readable gzip CSVs; 79,101 rows; 4,407 distinct security codes; no duplicate (Date, Code) within daily files. 3,545 rows have missing close/OHLC (can be normal no-trade rows). Artifact ZIP SHA256: `1ac7e82aca2a9fd8ce4273241baa48d4949a16e41a455c17a395c3b90a888da2`.
- Gzip validation and CSV integrity checks run offline. API source-level completeness against exchange master list and adjusted-price correctness have **not** yet been independently verified.
- GitHub API run listing: GET `https://api.github.com/repos/mleuatd/japan-stock-lab/actions/runs`; the connector's `fetch_workflow_run_jobs`, `fetch_workflow_job_logs`, `fetch_workflow_run_artifacts`, and `download_workflow_artifact` all worked. Fetching the workflow-specific /runs URL was blocked by URL allowlist, not lack of access.

## Changes after #1

- `validate_archive.py`: checks compressed files, exact headers, date/code consistency, duplicate codes, parseable numeric cells and row counts, tolerating valid empty OHLC.
- Workflow now audits archive before saving snapshot, and a change to the collector scripts/workflow on main triggers an additional run. Weekday schedule remains in place.

## Critical outstanding work

1. **Persistent PRIVATE archive:** current public repository deliberately ignores `archive/`. Neither Actions cache nor Artifact is durable. Before expiry, back up the ZIP to private storage. Do NOT commit API data into this public repo, or use a public Release/Pages. Review current J-Quants terms and any redistribution rules. A private storage/repository target plus a narrowly scoped write credential is needed for automated durable backup; this has not been configured.
2. Check subsequent run logs/artifacts and download/validate its outputs. Verify cache restored previously saved days and that subsequent collection skips them.
3. No trading calendar integration yet; dates with zero bars are retried in future runs, consuming API requests. Do not blindly mark all empty responses as permanent holidays.
4. A rate-limit policy, API quota monitoring, full-period completeness audit, durable incremental checkpoints, and multi-year historical backfill remain to be implemented.
5. Full-market rankings, Kochi shop/benefit matching, financial filters, and virtual trading/backtests have not yet been built.
6. Never disclose JQUANTS_API_KEY, never place collected API rows or generated CSVs in public GitHub.

## 2026-10-08 20:31 JST update: run #2 verified

- Run #2 https://github.com/mleuatd/japan-stock-lab/actions/runs/37769932666 completed successfully.
- Run #2 restored cache from run #1; skipped 18 stored market days; attempted 20 previously unfilled weekdays, saved 18 and got NO_DATA on 2024-10-14 and 2024-11-04.
- Output validator passed: **36 files, 158,194 rows, 4,414 distinct codes, 7,003 null-close rows**, range 2024-10-08 through 2024-11-28.
- Run #3 https://github.com/mleuatd/japan-stock-lab/actions/runs/37770638235 started, running at last check. Its final result has not yet been verified.
- New file `private_archive.py` supports optional durable backups in a separate **PRIVATE** GitHub repo. Needs `PRIVATE_ARCHIVE_REPO` GitHub Actions variable and `PRIVATE_ARCHIVE_TOKEN` secret (narrowly scoped Contents read/write). It downloads existing private daily files to restore cache gaps; sends only missing daily files when archiving. Unconfigured means cache + artifacts only. It has not yet been tested end-to-end with a real private destination.
- Collector default batch increased from 20 to 80 weekday requests. Already saved CSV dates skipped.
- `docs/index.html`: browser-only, IndexedDB-backed market filter prototype; handles locally loaded `.csv.gz`, never serves licensed rows on public Pages. Supports URL filters date/metric/code/minvol/limit, but links only work on browser already holding local market files. No live GitHub Pages URL until deployment configured.
- **Architecture decision:** compressed partitioned CSV is durable source-of-truth; an analytical DuckDB database should be constructed from those files in a private environment when advanced window functions/backtests are implemented. Avoid committing DuckDB database or raw bars in public repo. Derived metadata may include manifests with date, row counts, checksums but avoid public re-distribution of licensed data.
- Next steps: verify #3 successful; provision private storage; archive and restore full historical dataset; use exchange trading calendar to avoid retrying closed days; ensure staged backfill to all accessible dates; verify license before serving quotes publicly; add analytical query layer and more dashboard filters.

## 2026-10-08 22:00 JST update: Neon migration preparation

- Current GitHub Actions run #4: https://github.com/mleuatd/japan-stock-lab/actions/runs/37771766810 **completed / success**. Validated 174 day files; 766,639 rows; 4,504 distinct codes; 33,464 null-close rows; range 2024-10-08 to 2025-06-25. Collector reported 67 fetched, 107 skipped, 13 NO_DATA. Importantly, `PRIVATE_ARCHIVE_NOT_CONFIGURED` remains true: cache/artifacts are ephemeral.
- Neon connector actions inspected: no create_project/list_projects; `describe_project` without a project ID failed on unscoped connection. No Free project created; one-time owner UI provisioning still necessary. Never upgrade paid.
- Added `sql/001_init.sql` for PostgreSQL schema, `neon_import.py` for resumable private gzip CSV import (dry-run by default, write only with `--apply`), `tests/test_neon_import.py` for CSV parser cases and `docs/NEON_SETUP.md`.
- Not yet tested against a real Neon database; cannot claim completed DB ingest or full data durability. Keep raw J-Quants rows private. Do not set DATABASE_URL in public code and do not add direct public read API.
- Next after owner creates Free project: resolve Neon project ID; verify plan, database and Free quota; create schema and import a SMALL batch with storage measurement, then incremental chunks. Preserve existing ZIP artifact before it expires. Ensure an independent private archive destination; Neon is NOT a backup.
- Existing `docs/ZERO_COST_ARCHITECTURE.md` lists Turso as earlier preference; current user has explicitly selected Neon Free as target, pending measured storage suitability.

## 2026-10-08 23:07 JST: Neon Free live database created and verified

- After user resolved duplicate Neon projects, confirmed **project ID** `purple-bird-43526306`, name `japan-stock-lab`, region `aws-ap-southeast-1`, owner plan `free_v3`, and 1 GiB logical-size limit, on branch `br-misty-glitter-b3xota3q`.
- Initial default database was `neondb`; **kept untouched**, and created `japan_stock_lab` with owner `neondb_owner` using linked Neon connector. No paid products were enabled.
- Applied `sql/001_init.sql` to `japan_stock_lab` in a transaction, then verified four tables: `daily_bar`, `ingest_day`, `security_master`, `backtest_run`. Verified `SELECT current_database()` succeeds and `daily_bar` has **0 rows**. This is a REAL database schema, but raw stock archive has NOT been imported.
- Fixed SQL comment parsing in `neon_import.py`. It remains dry-run by default and needs PostgreSQL private `DATABASE_URL` and private archived CSVs to apply; no credential should be committed or exposed in public GitHub.
- Next: verify private durable archive restore and ensure repository Actions secret `DATABASE_URL` is set securely. Measure table footprint and quota BEFORE bulk import. Protect J-Quants private data; do not introduce public query endpoints, and do not start paid plans. Old cache/artifact is not guaranteed durable.

### Import workflow readiness (same session)
- Added manual-only `.github/workflows/import-neon.yml`. It requires existing private GitHub Actions secret `DATABASE_URL`, restores any available history cache/private archive, validates files, and imports at most **5** new trading days per run. No automatic schedule or paid Neon product. Workflow has NOT been run because `DATABASE_URL` is not known to be configured. Never enter it into the public repo/chat.
- `neon_import.py` now halts before each new day at >=700 MB measured database size and limits `--max-days` to 1..20. This protects against bulk imports but cannot guarantee that one day's import never exceeds the threshold. Monitor real Neon project consumption, and do not run if the account's Free budget is insufficient.
- Latest test importer workflow run https://github.com/mleuatd/japan-stock-lab/actions/runs/37789959012 completed successfully. Real Neon schema and empty row count were checked separately.
