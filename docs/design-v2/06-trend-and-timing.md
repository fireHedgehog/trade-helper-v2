# Trend & Timing — the signal engine

Both pages share one engine: a **two-sided Donchian-channel breakout** rule
(Turtle lineage). `features/signals/`, pure Python, deterministic (same
`bars` + `params` + `ENGINE_VERSION="donchian-1"` → identical output).
`donchian` is the only model in v1; the code is shaped so `ma_ensemble`,
`tsmom`, `structure`, chart-formation entries slot in as more `params.model`
branches later.

## The rule (`engine.py`, `indicators.py`, `params.py`)

Signal decided on the **close of bar `t`**, filled at `fill_at` (default
`open_next` = next session's open). Series: adjusted OHLC for equities, raw
OHLC for `*/USD` crypto (`data.load_ohlc`).

- **Entry** — close above the highest high of the last `entry_len` days → long;
  below the lowest low → short. Optional `use_ma_regime`: longs only above
  `SMA(ma_regime)`, shorts only below.
- **Exit**, first hit wins, checked every bar while open:
  1. **initial stop** `entry ∓ atr_stop_mult × ATR_entry` (Wilder ATR);
  2. **trailing stop** (`trail_mode`): `chandelier` = best-price-since-entry ∓
     `chandelier_k × ATR`, monotonic; or `exit_channel` = the `exit_len`
     Donchian; or `atr_trail` = `close ∓ atr_trail_k × ATR`;
  3. **model exit** — close back to an `exit_len`-day extreme against the
     position (`exit_len < entry_len`, the asymmetric Turtle convention);
  4. **end of data** — still open, entry row with NULL `exit_*`.
  Optional `stop_and_reverse`: flip into the opposite position on a
  channel-reversal exit.
- **Costs** (`cost_bps`/side + `slippage_atr × ATR`) apply to the return maths
  only, never to stop levels. Gapped-through stops fill at the worse of open
  vs stop.

**Params** (`SignalParams`). Since migration `0014` the parameters are resolved
**per symbol** from the `signal_strategies` registry (`08-strategy-management.md`)
via `assets.strategy_id` / `crypto_assets.strategy_id`, not from the old single
`signal_config` preset. The frozen default `naive-donchian-v1` is
`entry_len 20, exit_len 20, atr_len 20, atr_stop_mult 2.0, trail_mode
chandelier, chandelier_k 3.0, fill_at open_next, cost_bps 5.0, slippage_atr
0.05, allow_long true, allow_short false`; Bond ETFs run
`naive-donchian-v1-slow-entry` (identical but `entry_len 100`). The engine still
honours `allow_long/allow_short` but every Run — single or universe — forces
both on, so the board always shows every short setup (long/short is a display
filter, see below).

## Metrics (`metrics.py`) — single-symbol, rule-only, costs included, not validated

- **Trade-level** (closed trades): trades / wins / losses, win rate, avg win %,
  avg loss %, payoff ratio, expectancy (per trade + in R), profit factor,
  **SQN** (`√N · mean(R) / std(R)`), avg/median bars held, max consecutive
  losses, avg MAE / MFE (ATR units), exposure.
- **Equity curve** (daily state-driven return series, costs in): total return,
  CAGR, annualised vol, Sharpe, **Sortino**, max drawdown + drawdown
  duration, **Calmar / MAR**.
- **vs buy & hold** of the same symbol: total return, CAGR, max drawdown.

`frontend/src/features/timing/metrics.ts` mirrors this for the client-side
long/short view recompute.

## Timing page — `/timing/:symbol?` (single symbol)

**Run is a live scratchpad — it persists nothing.** `POST /api/signals/preview
{symbol, params}` runs the engine (~0.2 s) with the parameters currently in the
form and returns the full payload; no DB write. `GET /api/signals/timing/
{symbol}` still returns the symbol's last *stored* run (the board's universe
run, or a legacy `/run`) — `stale` when newer `price_bars` exist,
`status:"not_computed"` before any stored run, `chart_cached:false` after a
universe run. `POST /api/signals/run {symbol}` (persisting, strategy-resolved)
is kept for the board / deep links but the Timing page no longer calls it.

`TimingPage.tsx`:
- **Symbol picker** — async-search `Autocomplete` over `/api/data/assets`
  (`active_only`, client-side relevance re-rank: exact symbol > prefix >
  substring > name-only) + `BTC/USD` / `ETH/USD`. Default `QQQ`; deep-link
  `/timing/:symbol` preselects.
- **Model** dropdown (donchian only for now) + **Run**.
- **Parameters & guide** (collapsed by default) — a plain-language "what this
  strategy is" block, an expandable entry/exit rationale, `helperText` on every
  field. The form **pre-fills from the symbol's resolved strategy** (via
  `GET /api/signals/strategies/resolve/{symbol}`) and re-resolves on symbol
  change. **No Save** — edits are live-only; to change what the board uses,
  assign a strategy on the Strategies page.
- **`TimingChart.tsx`** — `lightweight-charts` v5 **multi-pane**, price pane
  deliberately tall (total height 1040, stretch `[13,1.3,1.9,1.5,1.5]`):
  candles + Donchian channel + toggleable SMA/EMA (5/20/50/200) + Chandelier
  stop step-line + long/short entry/exit markers + auto **key-level** lines
  (prior 52-week H/L, all-time high, last confirmed swing H/L, current stop —
  labelled "was resistance → now support" etc.); then **volume / MACD (12,26,9)
  / RSI (14) / KDJ (9,3,3)** panes. **D/W/M** timeframe (client resample) ·
  **5D · 1M · 6M · 1Y · 5Y · Max** range · native zoom/pan. Donchian / stop /
  markers show on the Daily timeframe only.
- **Show: Long / Short** checkboxes (chart toolbar, default both) — a **pure
  display filter**: hides that side's markers + trade rows and recomputes the
  metrics + equity curve for the visible side (an approximation, labelled
  "that side's isolated contribution, not a re-run"). Does not touch the
  engine, params, or DB.
- **Equity curve** (strategy vs buy & hold + drawdown), **trade history
  table** (oldest → newest, incl. the open trade), **metrics summary** (3
  groups).

## Trend page — `/trend` (whole universe)

`POST /api/signals/run-universe` → `worker.submit("signal_universe")` → a
background job (`signals.service.run_universe`, run via `asyncio.to_thread` —
the loop is pure CPU / GIL-bound, so threads wouldn't parallelise it, and the
progress bar must stay live). It resolves `symbol → params` once from the
`signal_strategies` registry, then loops `assets.active` ∪ `crypto_assets` ∪
the flat `signals/watchlist.py::TREND_WATCHLIST`, chunk 25, running each symbol
with its own strategy's parameters (direction forced two-sided), per-symbol
wipe + write `signal_events` + `signal_symbol_stats` (with `strategy_id`)
**only** (no `signal_chart` — the board doesn't need it). One `signal_runs`
row `scope='universe'` is the domain record. Verified: ~678 targets, ~54 s
(SQLite fsync-bound, not compute), ≈ 203 long / 118 short / 354 flat.

`GET /api/signals/board` → `{long, short, flat}` (each sorted by `state_since`
desc — freshest entries on top) + `watchlist` — a **sectioned** list
(`TREND_WATCHLIST_SECTIONS`): Indices (`QQQ SPY DIA IWM`) · Semis/Software
(`SOXX IGV`) · Sector SPDRs (11 XL*) · Mega-cap 7 (MAG7) · Cross-asset
(`GLD USO BTC/USD`) — plus `strategies` (the registry with live assigned
counts). Or `status:"not_computed"`.

`TrendPage.tsx`: Model select · the reused
`<FetchPanel kind="signal_universe">` (button + progress + cancel) · the
**watchlist table** — one table with an Excel-style divider row (`colSpan`,
tinted, short, uppercase) per section, each name showing state · entry ·
unrealized % red/green · stop · **Vol 60d**, or "–" when flat · **Holding long /
Holding short / Flat** tables (all carry the Vol 60d column). `Vol 60d` is the
stored annualised 60-day return vol (`signal_symbol_stats.vol_60d`, migration
`0015`) rendered as a calm→turbulent severity chip — an escalating weather icon
(sun → cloud → drizzle → wind → storm) and a green→red colour ramp at 15 / 25 /
40 / 60 % thresholds; a reference for the "size by volatility" line, not a
signal. The Watchlist header has a collapsible **"Position allocation
(advisory)"** panel — static reference text (inverse-vol sizing,
~12% vol target, ~10% position cap, sleeve budgets 50/20/15/5/10, long-only
default with bonds + BTC as the short exceptions, weekly re-check) plus the
live per-strategy symbol counts. No portfolio engine — text only, from the
frozen research in `docs/strategy-experiments/naive-donchian-v1-result.md`. Symbol →
`/timing/:symbol` — where, because `latest_run_for_symbol` joins via
`signal_symbol_stats`, the universe run's trades / metrics / state are shown,
with an info banner: "press Run for the Donchian overlay, equity curve, and
long/short split".
