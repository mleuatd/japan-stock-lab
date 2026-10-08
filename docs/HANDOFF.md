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
