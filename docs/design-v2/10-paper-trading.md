# 10 — Paper trading (the stress test)

**Goal.** Run the frozen Naive Donchian V1 signals + P4 sizing **long-only**
against an **Alpaca paper account**, unattended, for months, and keep a clean
trade journal. The journal is the deliverable — "does the grind trend up or
down" is the question, not "how fast does it blow up".

**Long only.** Drop the short book entirely — it matches the frozen research
headline, and it sidesteps Alpaca's shortability rejections. The board still
*computes* short state for display; paper ignores it.

**Philosophy (from the ask).** Minimal. No per-trade risk limits, no daily
loss circuit-breaker, no manual order approval. Faithful reproduction of the
research, then watch. The one thing we do NOT reinvent is a fill simulator —
**Alpaca's paper account is the source of truth** for positions, fills, and
equity, mirrored into our DB so a reset can't erase the record.

## Can Alpaca do this — yes, incl. full trade history

- Paper trading is a separate account with its own key pair, base URL
  `https://paper-api.alpaca.markets`. Free, resettable from the dashboard.
  Same Trading API surface as live.
- New credential provider key **`alpaca_paper`** (the data key stays
  `alpaca`). Store base URL + key in `credentials`.
- Market/limit/stop/trailing/bracket orders, fractional + notional orders,
  crypto 24/7. No commodities / FX. Rate limit 200 req/min — a daily batch of a
  few hundred orders is fine.

**History — every open and close is pullable:**

| Endpoint | Gives |
| --- | --- |
| `GET /v2/account/activities?activity_types=FILL` | every fill / partial fill — symbol, side, qty, price, ts, order_id. Paginated, date-filterable. The authoritative fill log. |
| `GET /v2/orders?status=all` | every order ever — open / filled / canceled / **rejected** / expired, with `filled_qty`, `filled_avg_price`, `submitted_at`, `filled_at`, reject reason. |
| `GET /v2/account/portfolio/history` | the equity / P&L time series (1Min…1D over 1D…all). The equity curve — one call, not maintained by us. |
| `GET /v2/positions` | current positions only (no history) — so the daily position snapshot is still ours. |

**Reset caveat.** Resetting the paper account **wipes** Alpaca's
activities / orders / portfolio history. So each reconcile **mirrors** the new
activities + orders + portfolio-history rows into our `paper_*` tables — those
are the durable research record across runs and resets.

## Will it get stopped out and lose everything on day 1 — no (unless you crank it)

With faithful **P4 sizing** each position is ~0.3–0.5 % of NAV before the
vol-target scalar, less after; a stop-out is ≈ −1R ≈ −0.2 % NAV. Fifty stops in
a bad week ≈ −10 %, not −100 %. The 12 % vol target + gross ≤ k_max cap is
exactly the thing that stops the day-1 blow-up. So the honest expectation is a
**grind**, not a fast death — and the real question is the multi-month drift.
The "lose it all fast" scenario only happens if you raise `k_max` / turn the
vol-target off, which the sizing params let you do if you want the aggressive
run.

## Components

### A. Broker client — `providers/clients/alpaca_trading.py`

Thin wrapper over the paper Trading API: `get_account()`,
`list_positions()`, `list_open_orders()`, `submit_order(symbol, side, qty|notional, type="market", tif="day")`,
`cancel_all_orders()`, `close_position(symbol)`,
`portfolio_history()` (for the equity curve — don't reconstruct it).

### B. Target book — the real sizing algorithm (`features/paper/target.py`)

A **Python port of the `sizing/engine.ts` waterfall** (spec: `09-position-sizing.md`).
Backend-authoritative; the Sizing sandbox should then call it via a new
`GET /api/signals/target-book` instead of computing client-side (kills the
TS/Python divergence). Each daily run:

1. Read the latest **universe run** (`signal_symbol_stats`): state, entry,
   `current_stop`, `vol_60d` per symbol.
2. `NAV` ← `account.portfolio_value` (live). `deployed by sleeve` ←
   `list_positions()` grouped by `assets.sector` (live — this is the
   "no live data" gap the sandbox had; the paper account *is* the live state).
3. Waterfall: inverse-vol → per-name cap → per-sector cap → 12 % vol target
   (de-lever only, k_max = 1) → optional macro overlay (latest `ai_regime` /
   naive composite zone).
4. Output `target_qty` per symbol (0 for flat / off-signal), long +, short −.

### C. Reconcile — `features/paper/reconcile.py` (a `worker` job `paper_reconcile`)

Once per trading day, ~09:35 ET (matches `fill_at: open_next`):

1. `cancel_all_orders()` (clear yesterday's unfilled).
2. `target` = B; `current` = `list_positions()`.
3. Per symbol: `delta = target_qty − current_qty`. Skip if
   `|delta| × price < min_ticket` ($ threshold) or
   `|delta| / max(|target|, ε) < rebalance_band` (default ~15 % — anti-churn,
   not a risk limit; matches "don't fiddle between rebalances").
4. Submit market `day` orders for the deltas (long only — buy to open, sell to
   close). A rejected order → log it and move on.
5. Sanity clamp: refuse the whole batch if target gross > 2× NAV (config bug
   guard, not a strategy limit).
6. ~15 min later: mirror new fills / orders / portfolio-history into `paper_*`.

**Exits.** Signal-driven only — no native stop orders. When the daily backtest
marks a position exited (stop / Donchian reversal / flip), the next reconcile
closes it at the open. This is the faithful reproduction; the journal then tells
us whether "exit at next open after a close-based stop" survives real gaps.

### D. The journal (`schema/migrations/00NN_paper.sql`)

| Table | Row |
| --- | --- |
| `paper_experiments` | one per run — name, `alpaca_paper` cred key, universe (`full` \| `watchlist` \| custom), start_nav, started_at, status. Every row below carries `experiment_id`. |
| `paper_runs` | one per reconcile — ts, NAV before/after, target gross, orders submitted/filled/rejected, macro zone used, sizing-params JSON |
| `paper_orders` | mirror of `/v2/orders` — symbol, side, qty, submitted_at, alpaca_order_id, status, filled_qty/avg_price/at, reject reason, the `signal_events.id` that triggered it |
| `paper_fills` | mirror of `/v2/account/activities?FILL` — the authoritative fill log |
| `paper_positions_daily` | our EOD snapshot — date, symbol, qty, avg_entry, market_value, unrealized_pl, current_stop |
| `paper_equity` | mirror of `/v2/account/portfolio/history` — date, equity, pl, pl_pct |
| `paper_trades` | matched round-trips — entry/exit price + date, realized P&L, R multiple, bars held, exit_reason (mapped from the signal), fill slippage vs the backtest's open |

The round-trip matcher (open → close per symbol) produces the "clean trading
journal". Every trade links back to its `signal_events` row (why it exists).

### E. UI — `/paper` (minimal)

Equity curve (from `portfolio_history`) · positions table (symbol, qty, entry,
mark, unrealized, stop, days held) · order log · the trade journal (closed
round-trips with R / P&L / reason / slippage) · **Reconcile now** and
**Flatten all** buttons · a `paper_enabled` kill switch. Reuse the density +
mini-chart components.

### F. Orchestration

Manual **Reconcile now** button first (via `worker.submit("paper_reconcile")`).
Add a daily cron once it's proven. One continuous run from a fixed start NAV
(e.g. $100k). **Do not reset mid-experiment** — a blow-up is a result. Reset
only for a new experiment version.

## Experiments

Two runs, in **parallel on two `alpaca_paper` accounts** (Alpaca allows
several), keyed by `experiment_id`:

- **A — full universe, long only.** Every `long` on-signal name (~200) + crypto
  longs, P4 sizing. Lots of trades, fast signal; may draw down hard in
  days/weeks. The "what the whole Donchian long book does live" journal.
- **B — watchlist only, long only.** The curated ~26. Signals sparse → can run
  months with capital intact. The "is the disciplined small book net-positive
  over time" journal.

**Monte Carlo is a backtest-side thing, not a live-paper thing.** A live paper
account plays out **one path at wall-clock speed** — you can't compress it. If
B is too quiet to be informative, the complement is a **block-bootstrap on the
frozen Donchian P4 daily-return series** (a `docs/strategy-experiments/` script)
→ a distribution of CAGR / maxDD / terminal wealth / P(ruin) over 10k resampled
paths, in seconds. Repeated live runs (reset → run again) are the slow
ground-truth for that distribution; the bootstrap is the fast estimate.

## The hard / risky parts (assessment)

1. **Sizing port + single source of truth.** Reimplement the waterfall in
   Python, point the sandbox at it, delete the client-side copy. ~1–2 days.
2. **Fills / slippage.** Market orders at 09:35 ≠ the backtest's exact-open
   fill. The journal measures the slippage the backtest ignored.
3. **Stops as next-open exits.** We eat the overnight gap (the backtest models
   "worse of open vs stop"). The journal tells us if that's survivable live.
4. **Reconcile edge cases** — partial fills, still-open orders (cancel-all
   first), negative buying power (the 2× clamp), halts / delistings on single
   names (log, strand, move on — no handling).

## Not building (per "don't over-engineer")

Per-trade risk limits · daily loss limit · position-count cap · manual order
approval · a real-money path · smart execution · our own fill simulator · a
short book.

## Phasing / effort

| Phase | Work | ~Effort |
| --- | --- | --- |
| 0 | `alpaca_paper` cred + `alpaca_trading` client + read-only `/paper` showing the paper account (proves the link) | ½ day |
| 1 | Python `target_book()` + `/signals/target-book` + sandbox points at it | 1–2 days |
| 2 | `paper_reconcile` job — target → cancel → deltas → fills → snapshot; manual button | 1–2 days |
| 3 | `paper_*` tables + round-trip matcher + `/paper` UI + Flatten all | 2–3 days |
| 4 | daily cron; then let it run for months | ½ day |

Total ≈ 1–1.5 weeks focused, for a faithful minimal system.
