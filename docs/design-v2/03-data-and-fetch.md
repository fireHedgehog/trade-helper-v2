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
| **Alpaca** Market Data | stock bars, crypto bars, option snapshots | Stock requests use `feed=sip`; the app requests through the prior weekday in America/New_York, plus any configured extra lag. A recent-data rejection can move the requested endpoint back. Options use the indicative snapshot feed. |
| **Alpaca** Trading | asset catalog | `/v2/assets` active + inactive, one call each. |
| **FRED** | macro series + commodity spot | 120 req/min; one call returns a full daily history. Values revised → store latest vintage + re-pull trailing 90 days each run. |
| **Issuer sites** | index / sector / theme membership | SSGA SPDR daily-holdings XLSX, Nasdaq-100 list API, iShares CSV, ARK CSV. `User-Agent: Mozilla/5.0`, ≥2 s spacing. Minimal stdlib XLSX reader. |

## Fetch kinds

| Kind | Handler | What it does |
| --- | --- | --- |
| `asset_catalog` | `catalog.py` | Upsert the full Alpaca equity + crypto catalog (metadata). Then `universe.recompute_active_universe()`. |
| `asset_prices` | `prices.py` | Raw and adjusted daily bars merged by date. Incremental starts 30 calendar days before each symbol’s last stored date and compares adjusted OHLC on overlapping dates. Changed values trigger a full-history fetch for that symbol before saving. A six-hour cooldown limits repeat checks, including when no new session exists. Batch size depends on history span. Full re-fetch bypasses cooldown and replaces returned historical rows from `history_start_date`. |
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

**Refresh everything** runs the existing operations sequentially: asset catalog →
memberships → asset prices → crypto → commodities → macro data → option snapshots →
Naive composite → Multisectional ranking → Trend. It defaults to incremental;
the full-history checkbox passes full mode to the existing fetches. Options
remain current snapshots. The baseline is computed from stored data on read;
this workflow never calls AI Macro or changes its saved assessment.

The overall bar measures completed steps plus the current fetch's target progress,
not estimated time. A failed step stops the sequence; Retry repeats that step.
Pause finishes the current step. App navigation preserves the sequence; a tab
reload restores it paused, and Resume checks any submitted fetch before continuing.
The browser keeps only the current workflow state in session storage.

Asset catalog · **Index & sector tags** (memberships + a group→members drill-down)
· Assets (server-paginated table, row → paginated bars) · Macro · Crypto ·
Commodities · **Options** (IV-grid coverage) · Run history. Endpoints under
`/api/data/*` (see doc 01 for the router list).

## Manual refresh and repair

Complete the price fetch and check its outcome before recomputing rankings and
running Trend. An interrupted or failed calculation can be rerun manually.
Incremental equity fetching repairs changed adjustment bases automatically. It
compares overlapping adjusted OHLC with relative tolerance `1e-8` and absolute
tolerance `1e-6`, then refetches the affected symbol from the earlier of its first
stored date and `history_start_date`. A repair must include every stored date and
the fetched tail, with adjusted data for every raw bar. Failed or incomplete
repairs keep the stored symbol data and report an error; successful repairs carry
a note in Run history and display the symbol while refetching.

The overlap detects changes in the recent stored month, not corrections confined
to older dates. Full equity re-fetch refreshes the entire historical raw/adjusted
basis and remains available for those older corrections. Rankings and signal results are cached separately and must be recomputed
afterward, including when the latest price date stays unchanged.

Membership sync marks absent members inactive per refreshed group and activates
the returned constituents. Asset-table tags show only active memberships; asset
detail also exposes inactive records. Membership does not create catalog assets:
catalog sync precedes membership sync so newly listed supported symbols can enter
the price-fetch universe. Departures keep their stored prices and remain active
if another auto-active group or the fixed seed includes them. These records describe
current membership, not historical entry/exit intervals for backtests.
