# Neon Free – guarded setup and import (2026-10-08)

## Status
The ChatGPT Neon connector in this session exposes database/schema operations, but **no list_projects or create_project action**. It cannot provision the project from an empty Neon account. The unscoped describe_project call failed because project_id is required. No Neon project/database was created or modified.

The owner must create exactly one **Free / $0** Neon project named `japan-stock-lab` in https://console.neon.tech/ and verify the selected plan before creation. Never select paid plans, paid compute, or overage features. Check no project already exists. The database should be named `japan_stock_lab` (create inside the Free project if not provisioned during setup). The assistant can then obtain project ID from the owner without asking for credentials, and use the linked Neon tools to examine/create database and schema.

## Import contract
- `sql/001_init.sql` creates only private PostgreSQL tables and indexes, no drops.
- `neon_import.py` does **not** call J-Quants; it reads existing private `archive/daily/**/*.csv.gz` and ingests one day per transaction.
- `ingest_day` records complete dates; subsequent imports skip them. PK prevents accidental duplicate `(trading_date,security_code)` inserts. If counts do not match, that day rolls back.
- Dry-run is default, and `--apply` is required for writes. A `DATABASE_URL` must be supplied securely via local environment or GitHub Actions Secret, never committed.
- No automatic GitHub Actions database push is enabled, because private archive and connection secrets are not yet configured and 1 GB Free quota must be measured first. Do **not** expose DB through public GitHub Pages; do not echo connection strings.
- Importing 766,639+ rows into a 1GB Free database could exceed capacity depending on row/index sizes. Test measured footprint with a small batch and monitor quota before a full import; stop if quota might be exceeded. Immutable private CSV archive is still required as independent recoverable backup.
- No real securities orders are implemented or permitted.
