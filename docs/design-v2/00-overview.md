# trade-helper-v2 — as-built design

A local-first, single-operator trading **research** app. It fetches market and
macro data into one SQLite file and presents six read-mostly pages. Nothing
here is a validated signal, a recommendation, or an order system — every score
and rule is labelled **naive-v1, descriptive, not statistically validated**.

This `docs/design-v2/` set describes the app **as it currently is** — a
snapshot that may be replaced wholesale (a future `design-v3`) rather than
edited forever.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, stdlib `sqlite3` (no ORM), pure-Python compute (no numpy/pandas) |
| Frontend | React + TypeScript + Vite, MUI v9, TradingView `lightweight-charts` v5, `@mui/x-charts` |
| Data | one SQLite file (`database/trade_helper.sqlite3`, git-ignored, **disposable**) |
| Providers | Alpaca (equities/crypto/options), FRED (macro/commodities), issuer holdings scrapes |
| Secrets | OS keychain via `keyring` — **never** in the DB, an API response, or a log |

## The seven pages

| Page | Route | What it answers |
| --- | --- | --- |
| **Macro** | `/macro` | Risk-on / risk-off right now — a transparent weighted composite of ~24 FRED series, plus an optional adversarial-LLM regime gauge. |
| **Multisectional** | `/multisectional` | Across the whole universe, which symbols look strongest by price/volume alone (cross-sectional ranking + leadership overlay + rebound watch). |
| **Trend** | `/trend` | Every symbol's current Donchian-breakout state — holding-long / holding-short / flat — as three sorted boards + a fixed watchlist strip. |
| **Timing** | `/timing/:symbol?` | The same rule drilled into one symbol: a broker-style multi-pane chart with entry/exit markers, a trade table, and standard performance metrics. Run is a live scratchpad — it saves nothing. |
| **Strategies** | `/strategies` | The parameter sets the Trend run uses. A minimal registry (`naive-donchian-v1` + a bond slow-entry variant); assign a strategy to a symbol selection. See `08-strategy-management.md`. |
| **Data management** | `/data-management` | The only place data enters the app — one paced background fetch per source, with a live progress bar. |
| **Credentials** | `/credentials` | Configure + verify provider keys. Data-driven from a provider registry. |

## Cross-cutting principles

- **Disposable DB.** Dropping the file and re-fetching is always safe and expected. Schema lives only in `schema/migrations/NNNN_*.sql`, applied forward-only on startup.
- **One instrument family per fact table.** Equities `price_bars`, crypto `crypto_bars`, commodities `commodity_prices`, macro `macro_observations`, options `option_chain_snapshots` — never mixed (keeps ML-style reads clean). Cross-family work joins on `date` at read time.
- **Cache the expensive, recompute the cheap.** The Macro composite recomputes live per request. The Multisectional ranking and the signal-engine runs are cached (a button recomputes, a `stale` flag shows when newer bars exist).
- **Not point-in-time.** Stored history is the latest vintage (survivorship + retroactive adjustment). Acceptable because the app only ranks/marks "now"; historical cross-sectional backtests are out of scope.
- **Paced, single-flight fetching.** One in-flight request per provider host, well under each rate limit. One background worker, one job at a time.

## Status (2026-08-31)

All seven pages are built and working end to end. The Naive Donchian V1
benchmark research is frozen (`docs/strategy-experiments/README.md`)
and its entry cluster is wired in via the `signal_strategies` registry. Depth
work remains (more signal models, walk-forward tuning, an options-analysis
page) — not new surfaces. Backend pytest suite passes; the frontend
type-checks.
