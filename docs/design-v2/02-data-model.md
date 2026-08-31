# Data model

All tables live in one SQLite file, defined only in `schema/migrations/`
(0001–0013). Grouped by instrument / concern family. `*_stats` tables are
maintained summaries so list views never scan the fact table.

## Equities / ETFs

| Table | Key | Notes |
| --- | --- | --- |
| `assets` | `symbol` | Full Alpaca catalog (active + inactive US equities). `active` = our price-fetch flag (see universe selection, doc 03). `sector` (GICS) + `market_cap` filled by the memberships sync. |
| `price_bars` | `(symbol, date)` | **Dual-basis**: raw `open/high/low/close/volume` + split/dividend-adjusted `adj_*`. `feed` ('sip' — see doc 03), `source`, `fetched_at`. Return maths use `adj_*`; the signal engine & charts use `adj_*` too (one basis end-to-end). |
| `price_bar_stats` | `symbol` | `bar_count, first_date, last_date, last_close, adv20_dollar, last_fetched`. |

## Crypto

| Table | Key | Notes |
| --- | --- | --- |
| `crypto_assets` | `symbol` | Alpaca crypto catalog; only `BTC/USD`, `ETH/USD` are `active`. |
| `crypto_bars` | `(symbol, date)` | Raw OHLCV only — no adjustment concept, 24/7. |
| `crypto_bar_stats` | `symbol` | as `price_bar_stats` minus the adjusted fields. |

## Commodities (FRED daily spot)

| Table | Key | Notes |
| --- | --- | --- |
| `commodity_series` | `instrument` | Seeded: WTI (`DCOILWTICO`), Brent (`DCOILBRENTEU`), Gold (`GOLDPMGBD228NLBM`), NatGas (`DHHNGSP`). Single daily price, no options. Gold/silver are effectively covered by GLD/SLV in `price_bars`. |
| `commodity_prices` | `(instrument, date)` | one `price` per day. |
| `commodity_price_stats` | `instrument` | summary. |

## Macro (FRED)

| Table | Key | Notes |
| --- | --- | --- |
| `macro_series_catalog` | `series_id` | ~30 series across `inflation / rates / growth / labor / risk / money-fx` (incl. WTI + Brent as macro series). FRED metadata + `tracked`. |
| `macro_observations` | `(series_id, date)` | latest-vintage `value` (`"."` → NULL). Each incremental run also re-pulls the trailing `fred_revision_lookback_days` (90). |
| `macro_obs_stats` | `series_id` | summary. |

No persisted "macro regime" — the composite is computed live (doc 04).

## Memberships (issuer-holdings scrapes)

| Table | Key | Notes |
| --- | --- | --- |
| `membership_groups` | `group_key` | `SP500`, `NDX`, `DJIA`, 11 sector SPDRs (`XLB…XLY`), theme ETFs (`XBI`, `SOXX`, `IGV`, `ARKX`). `gics_sector`, source url, sync timestamps. |
| `symbol_memberships` | `(symbol, group_key)` | `weight`, `active`, `last_seen`. Drives `assets.sector` (single sector-SPDR membership → GICS) and the auto-active universe. |

## Options (Alpaca, indicative feed)

| Table | Key | Notes |
| --- | --- | --- |
| `options_research_set` | `underlying` | Fixed 10: `SPY QQQ` + MAG7 + `SMH`. `bucket`. |
| `option_contracts` | `contract_symbol` (OCC) | thin: underlying/expiration/strike/type/style/status. |
| `option_chain_snapshots` | `(underlying, snapshot_date, contract_symbol)` | The daily **IV-surface grid** (6 tenors × 7 moneyness points): bid/ask/last/mid, `iv`, greeks (delta/gamma/theta/vega/rho), `underlying_price`, `feed='indicative'`. Idempotent per day; **no backfill** — history accrues forward one `snapshot_date` per run. |
| `option_snapshot_stats` | `underlying` | summary. |

## Macro AI regime

| Table | Key | Notes |
| --- | --- | --- |
| `ai_regime_runs` | `id`, UNIQUE `trading_date` | One row per day-cached run: `model`, `budget`, `prompt_version`, `score` / `confidence` (calibrated) + `_raw`, structural vote tallies, `summary`, `naive_score`, `weights_json`, `code_weighted_score`, `reconciler_score`, bounded `event_overlay`, `calibration_notes`, token/cost. |
| `ai_regime_messages` | `(run_id, …)` | full prompt/response audit per persona + reconciler. |
| `ai_regime_votes` | `(run_id, persona)` | vote / conviction / rationale (draft table; the live path uses `ai_regime_messages`). |

## Signal engine (Trend / Timing)

| Table | Key | Notes |
| --- | --- | --- |
| `signal_strategies` | `id` (one `is_default=1`) | Named parameter snapshots (migration `0014`): `key`, `name`, `params_json`, `note`. Seeded with `naive-donchian-v1` (default) and `naive-donchian-v1-slow-entry` (bond exception, `entry_len` 100). Immutable — a new set is a new row. See `08-strategy-management.md`. |
| `signal_config` | `id` (one `is_active=1`) | Vestigial single preset — kept as a fallback, no longer read for the board. (`profile` column lingers from a reverted two-library experiment.) |
| `assets.strategy_id` / `crypto_assets.strategy_id` | — | Which `signal_strategies` row a symbol runs. Explicit on every active row (default → V1, `ETF_BONDS` → slow-entry); NULL falls back to the default. |
| `signal_runs` | `run_id` | One per Run. `scope ∈ {single, universe}`, `symbol` (single only), `params_json` (a resolver marker for universe runs), `engine_version`, `status`, counts. |
| `signal_events` | `id` | The trade list: `direction`, `entry_date/price`, `exit_date/price/reason` (NULL while open), `bars_held`, `return_pct`, `return_r`, `mae_atr`, `mfe_atr`, `initial_stop`. Index `(symbol, entry_date)`. |
| `signal_symbol_stats` | `(run_id, symbol)` | Cached board state + `metrics_json` + the exact `params_json` and `strategy_id` used: `state ∈ {long,short,flat}`, `state_since`, `entry_price`, `last_close`, `unrealized_pct`, `current_stop`, `vol_60d` (annualised 60-day return vol, a board reference column). |
| `signal_chart` | `(run_id, symbol)` | Timing-only chart payload JSON: `{overlays (donchian_up/dn, stop_line), equity, key_levels, daily}`. **Not** written by universe runs. |

**Invariant:** a symbol has at most one `signal_symbol_stats` row at a time —
`wipe_symbol` deletes its `signal_events` / `signal_symbol_stats` /
`signal_chart` before each write (full recompute, single or universe). So the
"current" run for a symbol = whichever ran last.

## Multisectional ranking

| Table | Key | Notes |
| --- | --- | --- |
| `ranking_runs` | `id` | JSON-blob snapshots: `computed_at`, `latest_price_date`, counts, `payload_json`. Last 30 kept. |

## Operational

| Table | Key | Notes |
| --- | --- | --- |
| `fetch_runs` | `id` | One per fetch/worker job: `kind`, `mode`, `scope`, `status` (`queued→running→succeeded/failed/cancelled`), `planned/completed/failed_targets`, `rows_written`, `requests_made`, `current_target`, timestamps, `error_summary`. |
| `fetch_run_items` | `(run_id, target)` | per-symbol/series outcome: `status`, `rows_written`, `requests_made`, coverage dates, `duration_ms`, `error`. |
| `credentials` | `provider_key` | provider config + verification status only — **never a secret value**. |
| `schema_migrations` | `version` | applied migration ledger. |
