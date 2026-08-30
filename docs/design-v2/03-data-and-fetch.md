# Data acquisition & the Data Management page

The only place data enters the app. Each source is one **fetch kind** run by
the single background worker (doc 01). The page (`features/data-management/`)
is one `<FetchPanel kind=…>` per source: a button → `POST /api/data/runs` →
polls `GET /api/data/runs/{id}` → `LinearProgress` + live counters + Cancel.
`FetchPanel` re-attaches to an in-flight run on mount (via
`/api/data/runs/active`), so a refresh doesn't lose progress.

## Providers

| Provider | Used for | Limits / notes |
| --- | --- | --- |
| **Alpaca** Market Data | stock bars, crypto bars, option snapshots | Free "Basic": 200 req/min. **`feed=sip`** for stock bars — consolidated tape back to 2016-01-04 with real market-wide volume (the `iex` feed only archives ~mid-2020 and carries ~3% of volume). SIP's most recent ~15 min is not readable, so requests end at `today − alpaca_sip_end_lag_days` (1). Options: `feed=indicative`, 15-min delayed, chain snapshot only (no history). |
| **Alpaca** Trading | asset catalog | `/v2/assets` active + inactive, one call each. |
| **FRED** | macro series + commodity spot | 120 req/min; one call returns a full daily history. Values revised → store latest vintage + re-pull trailing 90 days each run. |
| **Issuer sites** | index / sector / theme membership | SSGA SPDR daily-holdings XLSX, Nasdaq-100 list API, iShares CSV, ARK CSV. `User-Agent: Mozilla/5.0`, ≥2 s spacing. Minimal stdlib XLSX reader. |

## Fetch kinds

| Kind | Handler | What it does |
| --- | --- | --- |
| `asset_catalog` | `catalog.py` | Upsert the full Alpaca equity + crypto catalog (metadata). Then `universe.recompute_active_universe()`. |
| `asset_prices` | `prices.py` | Daily bars for `assets.active`. **Dual-basis** = two passes per batch (`adjustment=raw` + `adjustment=all`), merged on `date`. **Skips** any symbol whose `price_bar_stats.last_fetched` calendar date (UTC) is today, with zero requests (bumped even on a no-new-bars result). **Batches** the rest — grouped by start date, one raw + one adj request per ≤150-symbol batch. A full daily run over ~676 names ≈ 8–12 requests; a same-day re-run ≈ 0. `mode="full"` ignores the skip and re-pulls from 2016. |
| `crypto_bars` | `crypto.py` | `BTC/USD`, `ETH/USD` daily bars, one pass. |
| `commodity_prices` | `commodities.py` | WTI / Brent / Gold / NatGas from FRED. |
| `macro` | `macro.py` | ~30 FRED series → `macro_observations` (+ trailing-90d revision re-pull). |
| `memberships` | `memberships.py` | Scrape the issuer holdings; write `membership_groups` + `symbol_memberships`; derive `assets.sector`; fill NDX `market_cap`; then `recompute_active_universe()`. First run item per group + `derive-sectors` + `recompute-universe`. |
| `option_snapshots` | `options.py` | For each of the 10 `options_research_set` underlyings: one `/v1beta1/options/snapshots/{u}` call over a ±20% strike / ≤190d band, then keep a fixed **grid** — 6 tenors (nearest listed expiry to 7/30/60/90/120/180 DTE) × 7 moneyness points (−15/−10/−5% → puts, ATM → both, +5/+10/+15% → calls). ≈480 rows/day, 10 requests. A name with no `price_bars` is skipped. |
| `signal_universe` | `signals.service.run_universe` (via `asyncio.to_thread`) | The Trend-page whole-universe backtest — see doc 06. |

## Universe selection — `assets.active`

`universe.recompute_active_universe()` (runs at the end of the catalog sync
**and** the memberships sync):

```
active = SEED_ACTIVE_SYMBOLS  ∪  current members of AUTO_ACTIVE_GROUPS
```

- `SEED_ACTIVE_SYMBOLS` (`universe.py`, ~430) — every ETF we want bars for (indices, factors, bonds, 11 sector SPDRs, ~50 theme ETFs, commodities) + companies not in any auto-active group but worth tracking (foreign ADRs, recent IPOs, divergence-pair names). Editable named groups, deduped.
- `AUTO_ACTIVE_GROUPS` = `SP500, NDX, DJIA` + the 11 sector SPDRs + `SOXX` + `ARKX`. Their scraped constituents are folded in automatically, so a new index addition is tracked on the next memberships sync — no code change. `XBI` / `IGV` are deliberately excluded (≈250 micro names).
- Current count ≈ **676**. Seed names not in the Alpaca catalog (recent M&A delistings) are logged and simply not fetched.

## Data Management page panels

Asset catalog · **Index & sector tags** (memberships + a group→members drill-down)
· Assets (server-paginated table, row → paginated bars) · Macro · Crypto ·
Commodities · **Options** (IV-grid coverage) · Run history. Endpoints under
`/api/data/*` (see doc 01 for the router list).
