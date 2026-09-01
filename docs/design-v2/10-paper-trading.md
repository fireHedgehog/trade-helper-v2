# 10 — Paper trading (the stress test)

**Goal.** Run the frozen Naive Donchian V1 signals + P4 sizing against an
**Alpaca paper account**, unattended, for months, and keep a clean trade
journal. The journal is the deliverable — "does the grind trend up or down" is
the question, not "how fast does it blow up". Full universe, not the watchlist.

**Philosophy (from the ask).** Minimal. No per-trade risk limits, no daily
loss circuit-breaker, no manual order approval. Faithful reproduction of the
research, then watch. The one thing we do NOT reinvent is a fill simulator —
**Alpaca's paper account is the source of truth** for positions, fills, and
equity.

## Can Alpaca do this — yes

- Paper trading is a separate account with its own key pair, base URL
  `https://paper-api.alpaca.markets`. Free, resettable from the dashboard.
  Same Trading API surface as live (orders / positions / account).
- New credential provider key **`alpaca_paper`** (the data key stays
  `alpaca`). Store the base URL + key in `credentials` like every other
  provider.
- Paper supports: market/limit/stop/trailing/bracket orders, fractional +
  notional orders, **shorting** (marginable + shortable + ETB names only —
  expect 20–40 % of the short book to be rejected), crypto 24/7. No
  commodities / FX (as everywhere).
- Rate limit 200 req/min — a daily batch of a few hundred orders is fine.

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
4. Submit market `day` orders for the deltas. A rejected short → log it
   ("wanted short X, not shortable") and move on; the realized book will
   legitimately differ from the theoretical one.
5. Sanity clamp: refuse the whole batch if target gross > 2× NAV (config bug
   guard, not a strategy limit).
6. ~15 min later: poll fills, write the journal.

**Exits.** Signal-driven only — no native stop orders. When the daily backtest
marks a position exited (stop / Donchian reversal / flip), the next reconcile
closes it at the open. This is the faithful reproduction; the journal then tells
us whether "exit at next open after a close-based stop" survives real gaps.

### D. The journal (`schema/migrations/00NN_paper.sql`)

| Table | Row |
| --- | --- |
| `paper_runs` | one per reconcile — ts, NAV before/after, target gross, orders submitted/filled/rejected, macro zone used, sizing-params JSON |
| `paper_orders` | every order — symbol, side, qty, submitted_at, alpaca_order_id, status, filled_qty/avg_price/at, reject reason, the `signal_events.id` that triggered it |
| `paper_positions_daily` | EOD snapshot — date, symbol, qty, avg_entry, market_value, unrealized_pl, current_stop |
| `paper_equity` | date, portfolio_value, cash, long_mv, short_mv (or just mirror `portfolio_history`) |
| `paper_trades` | matched round-trips — entry/exit price + date, realized P&L, R multiple, bars held, exit_reason (mapped from the signal), max fill slippage vs the backtest's open |

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

## The hard / risky parts (assessment)

1. **Sizing port + single source of truth.** Reimplement the waterfall in
   Python, point the sandbox at it, delete the client-side copy. ~1–2 days.
2. **Shortability.** ~20–40 % of the short book will be rejected. The journal
   records it — a genuine finding (the frozen backtest assumed you could short
   everything).
3. **Fills / slippage.** Market orders at 09:35 ≠ the backtest's exact-open
   fill. The journal measures the slippage the backtest ignored.
4. **Stops as next-open exits.** We eat the overnight gap (the backtest models
   "worse of open vs stop"). The journal tells us if that's survivable live.
5. **Reconcile edge cases** — partial fills, still-open orders (cancel-all
   first), negative buying power (the 2× clamp), halts / delistings on single
   names (log, strand, move on — no handling).

## Not building (per "don't over-engineer")

Per-trade risk limits · daily loss limit · position-count cap · manual order
approval · multi-strategy / multi-account · a real-money path · smart execution
· our own fill simulator · watchlist-only mode.

## Phasing / effort

| Phase | Work | ~Effort |
| --- | --- | --- |
| 0 | `alpaca_paper` cred + `alpaca_trading` client + read-only `/paper` showing the paper account (proves the link) | ½ day |
| 1 | Python `target_book()` + `/signals/target-book` + sandbox points at it | 1–2 days |
| 2 | `paper_reconcile` job — target → cancel → deltas → fills → snapshot; manual button | 1–2 days |
| 3 | `paper_*` tables + round-trip matcher + `/paper` UI + Flatten all | 2–3 days |
| 4 | daily cron; then let it run for months | ½ day |

Total ≈ 1–1.5 weeks focused, for a faithful minimal system.
