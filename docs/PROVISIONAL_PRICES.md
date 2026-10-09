# Provisional recent Japanese prices — zero-cost, two-stage design (2026-10-09)

## Requirement and boundaries
Keep **all costs at JPY 0**, private-only raw market data, no broker orders, and no scraping from sources prohibiting automated download. A displayed free price quote alone does not grant permission for automated bulk collection or durable storage.

J-Quants Free is delayed approximately 12 weeks (JPX confirms). Recent dates are therefore not available from that authoritative source. The existing full daily history stays in `daily_bar`.

## Implemented in live private Neon

`sql/003_provisional_prices.sql` creates:
- `provisional_bar`: small separate staging storage for permitted outside OHLCV, uniquely keyed by `(trading_date,security_code)`, with `source_name`, `source_uri`, `fetched_at`. No duplicate final daily-bar data inserted.
- `daily_bar_best_available`: non-materialized union. J-Quants `daily_bar` wins on any key collision; only still-unconfirmed provisional rows are returned for other keys, with `is_provisional=true` and original `price_source` so UI/backtests can exclude them or display a warning. Missing adjusted prices and trading value remain NULL, never manufactured.
- 2 indexes on provisional table (PK and code/date) for time/date access, but a **zero-row** staging table currently uses minimal storage.

On 2026-10-09 the private database returned `provisional_rows=0`, `trusted_rows=1,914,081`, `combined_rows=1,914,081`, confirming the view doesn't alter or duplicate already-imported trusted history.

When J-Quants eventually supplies a date, normal importer inserts `daily_bar`; the view automatically stops serving provisional values for the same date/code. Deliberate retention/auditing of source rows is safer than deleting or overwriting before review. Do not copy a provisional adjusted close from another source.

## Sources checked and limitations
- JPX (official) provides TSE daily `株式相場表` with OHLCV, normally published the next business day, but public website rules restrict secondary use/redistribution and high-frequency automation; do **not** deploy an automatic bulk scraper without confirming permitted private automated use.
- Yahoo! Finance Japan explicitly bans programmatic/scraped collection. Do not scrape or impersonate browsers.
- Stooq advertises Japanese symbols and some free historical downloads, but coverage, terms authorizing automated downloading of 4,000+ instruments, consistent symbols/adjustments and retention are not verified. Don't enable it in Actions without tests and permission clarification.
- An individual's brokerage CSV may be permitted for the account holder to export manually, but may cover only positions/watchlists rather than entire Japanese market. A small manual export can be parsed into staging once a user-supplied permitted file is available.

## Next steps
1. Identify and verify a provider that permits at least private bulk programmatic downloads **for JPY 0** and sufficient ticker/date coverage (or get an explicit permission from JPX for private automation).
2. Implement a provider-specific fetcher under strict daily request caps, provenance and quality checks; test a few sample codes against J-Quants dates during overlap.
3. Import to `provisional_bar` with `ON CONFLICT (trading_date,security_code) DO UPDATE` only when validated newer same-source provenance exists, never replacing `daily_bar`.
4. Add diagnostics for coverage, missing codes, division-adjustment mismatch and finalization rate. Preserve original fetch timestamps and provider.
5. Add separate backtest options: authoritative-only by default, or knowingly opt into provisional. No data exposure on unauthenticated public GitHub Pages.

Do not claim recent prices are already collected until the provisional table actually has validated rows.


## 2026-10-09 source search update — verifiable free recent prices vs reusable bulk-feed access

- **JPX Tokyo Stock Exchange Daily Report** `https://www.jpx.co.jp/markets/statistics-equities/daily/index.html`: daily per-issue `株式相場表` PDFs are freely displayed; official site search indexed actual October 2026 files `/automation/markets/statistics-equities/daily/files/202610/stq_20261001.pdf`, `stq_20261002.pdf`, and other trading dates. The sample text contains ticker, session OHLC, closing price, daily volume and turnover. This is a credible primary-source **free display/download** candidate, but its web terms explicitly restrict repurposing / redistribution without permission and ask users to refrain from high-load automated acquisition. **Do not run a scraper or bulk import without explicit permission/licensing clarification.** Official terms: `https://www.jpx.co.jp/term-of-use/index.html`.
- **Stooq**: `.JP` ticker OHLC CSV historically free for personal download. As of 2026 CSV retrieval requires an API key obtained through CAPTCHA; no authenticated batch quota or fully permitted unattended CI workflow established. Free download is not equivalent to approved whole-exchange bulk replication; do not install an unattended downloader before authorizing use and testing code coverage. See `https://stooq.com/q/d/?s=7203.jp&get_apikey`. The key, if used, must be private GitHub Actions Secret only.
- **Twelve Data**: Free Basic advertises 800 credits/day, but detailed pricing offers **global trial symbols** rather than full Japanese market entitlement. Japan EOD market-wide access belongs to higher paid international plans, so Basic isn't a confirmed zero-cost solution for ~4,700 Tokyo symbols/day.
- **KABU+**: Tokyo-exchange-authorized automatic whole-market CSV is supported technically but is a paid membership, hence **excluded** under strict ¥0 policy.
- **JPX monthly quotes** `https://www.jpx.co.jp/markets/statistics-equities/price/index.html`: official free monthly per-stock aggregated OHLC; not equivalent to daily data needed for top-30 ranks.
- Yahoo/yfinance: unapproved bulk website extraction and potential blocking; not suitable for a permitted reliable free production pipeline.

**Outcome:** Found a free authoritative **daily publication** (JPX PDF), but **not yet a verified, licensed ¥0 unattended all-ticker daily feed**. Existing `provisional_bar` is empty; do not claim recent data ingestion. Next action is seek permission for low-rate personal automated archival/import of JPX PDFs or Stooq owner permission for a defined 4,700 symbols/day budget, or switch to consented manual PDF/CSV upload. Never publish raw licensed data through public GitHub Pages.
