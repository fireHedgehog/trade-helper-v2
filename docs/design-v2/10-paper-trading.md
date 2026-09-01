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

### D. The journal — every valuable datum (`schema/migrations/00NN_paper.sql`)

The point of the journal is that **years later you can answer "why was this
position this size on this day, and how did it work out"** — the decision
trail, the trade lifecycle, the book each day, and the derived research views.
Nothing is thrown away.

**Durable header — survives a paper-account reset:**

| Table | Row |
| --- | --- |
| `paper_experiments` | **the journal ID.** name, `alpaca_paper` cred key, universe (`full` \| `watchlist` \| custom), start_nav, started_at, ended_at, end_reason (`blew_up` \| `manual` \| `running`), final_equity, params_json (sizing params + strategy_id + engine_version). Every row below carries `experiment_id`. Never deleted. |

**The decision trail — the "流水账" (`paper_decisions`, one row per
reconcile × symbol that mattered):**

reconcile_date · symbol · in_universe · **the sizing waterfall snapshot at that
moment** — inverse-vol raw wt · after per-name cap (+ did it bind) · sleeve,
sleeve deployed %, sleeve headroom, after per-sector cap · est book vol,
vol-target scalar, after vol-target · **macro zone + macro scalar** · final
target wt / $ / shares · held_qty · target_qty · delta · **verdict** ∈
`ADD / TRIM / HOLD / EXIT / BLOCKED / SKIP` · **`reason` (one human string)**,
e.g.

- `ADD` — "new long; Tech sleeve 18% of 30% cap → room; macro neutral ×0.65; target 0.9% NAV, hold 0 → buy 12 sh"
- `TRIM` — "still long; vol-target scalar 0.80→0.62 (book vol 19%); target 0.6%→0.4%; sell 4 sh"
- `EXIT` — "Donchian exit stop_trailing on the 09-03 close; close 18 sh at next open"
- `BLOCKED` — "want +0.5% but Energy sleeve at 30% cap; no order"
- `HOLD` — "within the 15% rebalance band; no order"

Each decision links to the `signal_events.id` it came from and (if an order
resulted) to `paper_orders.id`.

**Orders & fills — mirrored from Alpaca:**

| Table | Row |
| --- | --- |
| `paper_orders` | `/v2/orders` mirror — side, qty, submitted_at, status, filled_qty / avg_price / at, reject reason, `decision_id`, **`ref_open` (that day's open) + `slippage` (fill − ref_open, bps and R)** |
| `paper_fills` | `/v2/account/activities?FILL` mirror — the authoritative fill log |

**The trade — matched round-trip (`paper_trades`):**

open (date, price, shares, opening `decision_id` + `signal_events.id`, entry
reason) · **adds/trims during the hold** (list of `decision_id` + reason) ·
exit (date, price, shares, exit reason from the signal's `exit_reason`) ·
**outcome** — realized P&L $ / % · **R multiple** (P&L ÷ initial risk =
(entry − initial_stop) × shares) · bars held · **MAE / MFE** (worst / best
mark-to-market during the hold, ATR units) · exposure-weighted return · **entry
context** (macro zone, book gross, this name's vol-60 and momentum rank at
entry).

**The book each day:**

| Table | Row |
| --- | --- |
| `paper_equity` | `/v2/account/portfolio/history` mirror — date, equity, cash, daily P&L $ / % |
| `paper_book_daily` | our aggregates — gross %, # positions, largest position %, largest sector %, trailing realised book vol, macro zone, vol-target scalar, cash-drag % |
| `paper_positions_daily` | per-name EOD mark — date, symbol, qty, avg_entry, market_value, unrealized_pl, current_stop, dist-to-stop |

**Derived research views** (nightly rollup or computed on read):

- **Live vs the frozen backtest**, side by side — win rate, avg win/loss %,
  payoff, expectancy in R, profit factor, SQN, avg/median hold, max consecutive
  losses. This comparison is the whole point.
- **Exit-reason breakdown** — % of closed trades by `stop_initial /
  stop_trailing / donchian_reversal / flip`, and the avg R of each bucket.
- **The stop-scratch question** — R distribution of trades that stopped out
  within N days of entry. A fat −0.8…−1R cluster in week one *is* the bleed the
  stress test is looking for, now measured.
- **Slippage summary** — mean / median fill slippage vs the assumed open, in
  bps and R; total drag over the run vs the backtest's `slippage_atr 0.05`.
- **Sizing-layer attribution** — how often each cap bound; average gross the
  vol-target scalar removed; average gross the macro overlay removed. Which
  layer costs return / does work.
- **Regime attribution** — P&L on risk-on vs neutral vs risk-off days; did the
  ×0.65 / ×0.35 throttle cut losses in bad regimes or just cap the upside.
- **Theoretical vs realised book** — symbols wanted but not gotten (halted, no
  data, cap-blocked).

### E. Page — **Paper Trading** (new nav item `/paper`)

A research page, not a trading terminal. Reuses the density + mini-chart
components. Layout:

1. **Experiment switcher** — pick a `paper_experiments` row (the journal ID):
   name · universe · start NAV · status · days running · equity · total return
   · maxDD.
2. **Equity panel** — curve + drawdown vs SPY buy-hold, with a gross-exposure
   overlay and regime-zone shading.
3. **Live vs backtest** — the small stats table (D, first bullet). The headline.
4. **Open positions** — symbol · shares · entry · mark · unreal $ / % / R ·
   days · stop · dist-to-stop · last decision reason. Mini-chart on expand.
5. **The ledger** — reverse-chronological `paper_decisions` ⋈ orders ⋈ fills:
   `[date] [symbol] ADD/TRIM/EXIT — reason — order N sh @ px (slippage) — P&L if
   closing`. Filter by symbol / verdict / date. This is the left-hand
   operations record tied to the right-hand trade record.
6. **Trade journal** — closed `paper_trades`, each an expandable story (entry
   reason → adds/trims → exit reason, R, P&L, MAE/MFE, hold, entry context).
   Sort by R / P&L / date.
7. **Research rollups** — the exit-reason breakdown, the stop-scratch
   distribution, slippage summary, sizing-layer + regime attribution (charts).
8. **Controls** (collapsed): Reconcile now · Flatten all · mark experiment
   ended · `paper_enabled` kill switch.

### F. Orchestration

Manual **Reconcile now** button first (`worker.submit("paper_reconcile")`).
Daily cron once proven. One continuous run per experiment from a fixed start
NAV (e.g. $100k). **Do not reset mid-experiment** — a blow-up is a result;
`end_reason = blew_up` and the journal stays. Reset only to start a new
experiment version (new `paper_experiments` row = new journal ID).

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
| 0 | `alpaca_paper` cred + `alpaca_trading` client + `paper_experiments` table + a read-only **Paper Trading** nav item showing the paper account (proves the link) | ½–1 day |
| 1 | Python `target_book()` + `/signals/target-book` + sandbox points at it (single source of truth) | 1–2 days |
| 2 | `paper_reconcile` job — target → decisions (with reason strings) → cancel → deltas → mirror orders/fills/equity → daily snapshot; manual **Reconcile now** button | 2–3 days |
| 3 | full `paper_*` schema + round-trip matcher + the `/paper` page (experiment switcher, equity, ledger, trade journal) + Flatten all | 3–4 days |
| 4 | research rollups (live-vs-backtest, exit-reason, stop-scratch, slippage, attribution) + block-bootstrap Monte Carlo script | 2 days |
| 5 | daily cron; then let A and B run for months | ½ day |

Total ≈ 2 weeks focused, for a faithful minimal system with a research-grade
journal.
