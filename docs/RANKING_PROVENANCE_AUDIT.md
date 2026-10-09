# Independent verification: ranking freshness and ingestion provenance

Verified on 2026-10-10 JST against private Neon database `japan_stock_lab` (read-only aggregate queries). This note does not contain licensed price rows.

## Ranking session-gap audit

`daily_change_rank` uses the previous available row for each code. That is potentially dangerous if a code has missing sessions: a multi-session change could be misrepresented as a one-session move. Check against the preceding session in the whole archive:

```sql
WITH calendar AS (
 SELECT trading_date, lag(trading_date) OVER (ORDER BY trading_date) AS previous_market_day
 FROM (SELECT DISTINCT trading_date FROM daily_bar) d
)
SELECT
 count(*) AS ranked_rows,
 count(*) FILTER (WHERE r.previous_trading_date <> c.previous_market_day) AS gap_rows,
 count(DISTINCT r.trading_date) FILTER
   (WHERE r.previous_trading_date <> c.previous_market_day) AS affected_dates
FROM daily_change_rank r JOIN calendar c USING (trading_date);
```

**Observed:** 1,811,285 ranked rows; 0 gap rows; 0 affected dates. For the currently stored rows, no stale previous-session comparison was detected. This does **not** prove every exchange session is present in the archive, nor future imports will preserve this property. The ranking view itself does not enforce same-session adjacency; rerun after ingestion.

The same check restricted to `daily_rank <= 30` found 12,960 top-30 entries and 0 gap rows.

## Import provenance audit

```sql
SELECT count(*) FILTER (WHERE state = 'complete') AS complete_days,
       count(*) FILTER (WHERE source_fetched_at IS NULL) AS unknown_source_fetch_times,
       count(*) FILTER (WHERE batch_id IS NULL) AS missing_batch_links,
       min(collected_at) AS earliest_recorded_collection,
       max(collected_at) AS latest_recorded_collection
FROM ingest_day;
```

**Observed:** 433 complete days; 433 rows missing `source_fetched_at`; 433 rows missing `batch_id`. `ingest_batch` is empty. Do not reconstruct original API fetch times from import timestamps: they are distinct events and historical fetch timestamps may be unknowable. This is a **provenance gap**, not evidence of missing market bars.

## Next engineering changes

1. Add an adjacency condition to ranking calculations or a recurring aggregate-only guard so later sparse imports cannot silently produce multi-day one-day returns.
2. For *future* imports, record actual batch IDs and source-fetch times only when reliably known. Keep historical unknown timestamps NULL.
3. Add tests with synthetic missing-session bars and split events before changing live views. Do not expose J-Quants rows publicly.
4. Reconcile the 433 trading days against an independent official trading calendar. A complete import manifest alone does not prove exchange completeness.
