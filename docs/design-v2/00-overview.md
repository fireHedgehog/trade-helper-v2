# trade-helper-v2 — as-built design

A local-first, single-operator trading **research** app. It fetches market and
macro data into one SQLite file and presents eight research pages. Nothing
here is a validated signal, a recommendation, or an order system — every score
and rule is labelled **naive-v1, descriptive, not statistically validated**.

This `docs/design-v2/` set describes the current application. It contains
feature behavior and operating assumptions, not change history.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, stdlib `sqlite3` (no ORM), pure-Python compute (no numpy/pandas) |
| Frontend | React + TypeScript + Vite, MUI v9, TradingView `lightweight-charts` v5, `@mui/x-charts` |
| Data | one SQLite file (`database/trade_helper.sqlite3`, git-ignored, **disposable**) |
| Providers | Alpaca (equities/crypto/options), FRED (macro/commodities), issuer holdings scrapes |
| Secrets | OS keychain via `keyring` — **never** in the DB, an API response, or a log |

## The eight pages

| Page | Route | What it answers |
| --- | --- | --- |
| **Macro** | `/macro` | Risk-on / risk-off right now — a transparent weighted composite of ~24 FRED series, plus an optional adversarial-LLM regime gauge. |
| **Multisectional** | `/multisectional` | Across the whole universe, which symbols look strongest by price/volume alone (cross-sectional ranking + leadership overlay + rebound watch). |
| **Trend** | `/trend` | Confirmed actions pending next open, simulated long/short/flat positions, and a fixed watchlist. |
| **Timing** | `/timing/:symbol?` | The same rule drilled into one symbol: a broker-style multi-pane chart with entry/exit markers, a trade table, and standard performance metrics. Run is a live scratchpad — it saves nothing. |
| **Strategies** | `/strategies` | The parameter sets the Trend run uses. A minimal registry (`naive-donchian-v1` + a bond slow-entry variant); assign a strategy to a symbol selection. See `08-strategy-management.md`. |
| **Sizing** | `/sizing` | A live parameter sandbox: given the board's on-signal names + a risk-ladder you drag, how big should each position be and what is holding it back. Places no order, adds no engine — pure arithmetic over the board. See `09-position-sizing.md`. |
| **Data management** | `/data-management` | The only place data enters the app — one paced background fetch per source, with a live progress bar. |
| **Credentials** | `/credentials` | Configure + verify provider keys. Data-driven from a provider registry. |

## Cross-cutting principles

- **Disposable DB.** Dropping the file and re-fetching is always safe and expected. Schema lives only in `schema/migrations/NNNN_*.sql`, applied forward-only on startup.
- **One instrument family per fact table.** Equities `price_bars`, crypto `crypto_bars`, commodities `commodity_prices`, macro `macro_observations`, options `option_chain_snapshots` — never mixed (keeps ML-style reads clean). Cross-family work joins on `date` at read time.
- **Cache the expensive, recompute the cheap.** The Macro composite recomputes live per request. The Multisectional ranking and the signal-engine runs are cached (a button recomputes, a `stale` flag shows when newer bars exist).
- **Not point-in-time.** Stored history is the latest vintage (survivorship + retroactive adjustment). Acceptable because the app only ranks/marks "now"; historical cross-sectional backtests are out of scope.
- **Paced, single-flight fetching.** One in-flight request per provider host, well under each rate limit. One background worker, one job at a time.

## Operating workflow

The operator completes data fetching, recomputes Multisectional rankings and
runs Trend before reviewing signals and sizing. Full price re-fetch repairs
historical adjustment bases; dependent rankings and signals require explicit
recomputation. AI regime generation is a separate manual action. Sizing compares
total target holdings with operator-entered exposure by sleeve. There is no
connected paper or live order execution.
