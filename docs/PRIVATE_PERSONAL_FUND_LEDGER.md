# Private personal fund ledger / Neon

**No personal balances, transaction amounts, screenshots or brokerage credentials may be committed to this public repository.** Real records belong only in the access-controlled Neon database, the owner's original ChatGPT Library Excel workbooks and locally exported offline backup files.

## Live schema (Neon: separate from stock-market research tables)

| Table | Purpose |
|---|---|
| `personal_fund_source` | Evidence/provenance of old Excel and new screenshots, with dates and uncertainty |
| `personal_fund_catalog` | Fund identifiers and NISA-side/taxable account group |
| `personal_fund_estimated_purchase` | Modeled monthly cash contributions, assumed investment date, NAV/10k units, theoretical and adjusted units, and source reference |
| `personal_fund_recurring_plan` | Recorded monthly plan; may not imply an actual executed purchase |
| `personal_fund_annual_estimate` | Historical asset values from reconstructed old Excel |
| `personal_fund_inferred_cashflow` | Principal increase evidenced by snapshots; September bucket is **tentative**, while actual execution date/units stay NULL |
| `personal_fund_snapshot` | Archived image-based observations: receipt date separate from actual valuation date |
| `personal_fund_position` | Fund-by-fund position balances, acquisition principal, unrealized gain/loss and source |

Useful read-only views: `personal_fund_monthly_chart`, `personal_fund_yearly_chart`, `personal_fund_asset_history_for_chart`, `personal_fund_position_change`, `personal_fund_snapshot_summary`, `personal_fund_monthly_cashflow_chart`.

**Important:** Historical contributions were inferred in the old Excel by applying recurring-plan assumptions to historical fund NAVs and then calibrating modeled units to observed account balances. These rows are **not executed broker transactions**. Model inputs include interpolated fund NAVs, adjusted estimated units and assumed purchase dates (some dates may be non-trading days). They must never be presented as independently verified executions. Do not backfill missing actual unit holdings from the statement's return percentage.

The newest screenshot is labeled with **date received**, not an unobservable price-as-of date; keep the actual valuation date NULL unless proven from an official brokerage statement.

## Local backup and charts

After connecting to your *private* Neon account in a controlled environment, run:

```bash
export DATABASE_URL='postgresql://...secret...'
python -m pip install 'psycopg[binary]>=3,<4'
python personal_fund_local_backup.py --output-dir /some/private/location/empty-directory
```

The output is a SQLite file containing the private tables and views, monthly/yearly summary CSVs and an accessible SVG chart of historical invested principal / market value / unrealized P&L. No private values appear in the public GitHub source or CI logs. The script rejects an output path inside this public GitHub repository and refuses to overwrite non-empty directories.

To inspect the current holdings in Neon without exporting files:

```sql
SELECT * FROM personal_fund_snapshot_summary ORDER BY received_on DESC;
SELECT * FROM personal_fund_monthly_chart ORDER BY purchased_month;
SELECT * FROM personal_fund_monthly_cashflow_chart ORDER BY period_month;
SELECT * FROM personal_fund_asset_history_for_chart ORDER BY month_key;
SELECT * FROM personal_fund_position_change ORDER BY account_group,fund_code;
```

Data quality checks:

```sql
SELECT source_key, count(*) AS rows, sum(contribution_yen) AS modeled_principal
FROM personal_fund_estimated_purchase GROUP BY source_key;

SELECT snapshot_key, count(*) AS funds,
  SUM(market_value_yen-invested_yen-unrealized_pnl_yen) AS balance_difference
FROM personal_fund_position GROUP BY snapshot_key;
```

## Future screenshot updates

1. Capture values per fund (market value, acquisition principal or gain/loss) from screenshots; deduce principal only when displayed gain/loss permits exact arithmetic.
2. Register the date when images were received; record the actual valuation date only if visible or independently sourced.
3. Add a new `personal_fund_snapshot` and new `personal_fund_position` rows; never overwrite prior historical positions.
4. Distinguish verified broker execution history from inferred Excel-model rows.
5. Run balance/row count checks, build comparative chart, and export to a **private** backup folder (not public GitHub).

The Neon account and the underlying private source documents remain required for durable storage; a public GitHub code backup alone does not include any financial records.
