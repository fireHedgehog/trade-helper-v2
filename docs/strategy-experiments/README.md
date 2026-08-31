# Strategy experiments — frozen guidance

This folder holds the **conclusions** of the strategy research, not the process.
It is the single reference for the app's first strategy version. **Do not delete
it.** When a genuinely different model is researched, add a sibling file here;
do not rewrite this one.

## For agents: do not go spelunking in history

The full experiment code and raw outputs (scripts, result CSV/JSON, interactive
HTML reports) lived under `backend/temp/` and `docs/temp/`. They were committed
**once** and then removed from the working tree. They are preserved only in git
history:

- commit **`c296945`** (`Freeze Naive Donchian V1: 5-stage research + strategy registry`)
- GitHub: `https://github.com/fireHedgehog/trade-helper-v2/tree/c296945/docs/temp`
  and `.../tree/c296945/backend/temp`

**Do not fetch, read, or "reproduce" that material to verify these numbers.**
The user does not care about exact reproduction, fingerprints, or whether a
figure is off by a basis point — this is an app, not a paper. Reading stale
historical files wastes tokens and context. Every number in this document is
**hardcoded on purpose** so nothing here depends on those files existing. Treat
the numbers below as given.

All figures are **descriptive and survivorship-inflated** (the universe is
today's index membership, i.e. known winners; there is no point-in-time
universe). What is trustworthy is the *ranking* of the rules, which was stable
across two cost levels, two universe definitions, and a robustness grid.

---

## FROZEN: Naive Donchian V1

Engine `donchian-1`. Price history 2016-01-04 → 2026-08-30. Universe = active
equities/ETFs ∪ active crypto ∪ the hard-coded `TREND_WATCHLIST` (~678 targets,
673 with ≥ 200 bars).

### Per-symbol signal — one knob differs between the two strategies

The engine has a single `exit_len` field; under the `c3_d20` exit it is the
Donchian-20 reversal-channel width. **The only parameter that differs between
the default and the bond exception is `entry_len` (20 vs 100)** — "100/50" was
Turtle notation and does not map to a second engine field here.

| Knob | Default (`naive-donchian-v1`) | Bond-ETF exception (`naive-donchian-v1-slow-entry`) |
| --- | --- | --- |
| `entry_len` | **20** | **100** |
| `exit_len` | 20 | 20 |
| `trail_mode` / `chandelier_k` | `chandelier` / 3.0 | same |
| `atr_stop_mult` / `atr_len` | 2.0 / 20 | same |
| `fill_at` | `open_next` | same |
| `cost_bps` / `slippage_atr` | 5.0 / 0.05 | same |
| `use_ma_regime` / `stop_and_reverse` | off | same |
| Direction (`allow_short`) | long only (`false`) — advisory only | `true` (bonds); also advisory-`true` for `BTC/USD` on the default |

Exact default `params_json`:
`{"model":"donchian","entry_len":20,"exit_len":20,"atr_len":20,"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,"warmup_buffer":10,"allow_long":true,"allow_short":false}`
The bond variant is the same with `entry_len:100`.

**Direction is not a board filter.** The Trend / universe run always computes
long *and* short for every symbol. The long/short *recommendation* (default long
only; Bond ETFs and `BTC/USD` two-sided; ETH long only) is surfaced in the UI,
not enforced — so a future short-capable strategy needs no re-fetch.

### Portfolio construction — rule P4 (no code, reference only)

Not implemented as code. The operator does not trade directly off it. It is
shown as static advisory text on the Trend watchlist.

1. **Inverse-vol position sizing** — `w_i ∝ 1 / σ_i`, `σ_i` = 60-day annualised
   stdev of the instrument's return; gross normalised to 100% across on-signals.
2. **Portfolio vol-target scalar** — multiply the book by
   `clip(0.12 / trailing_60d_portfolio_vol, 0, k_max)`.
3. **Caps** — per-position `|w_i| ≤ 10%` of NAV; gross `≤ k_max`.
4. **Fixed sleeve risk budgets** — equity 0.50 / bond 0.20 / commodity 0.15 /
   crypto 0.05 / other 0.10; inverse-vol within a sleeve; inactive sleeves'
   budget redistributed pro-rata.
5. **Weekly rebalance.**
6. **Leverage** — headline `k_max = 1` (unlevered, gross ≤ 100%); `k_max = 2`
   is a documented alternative.

Dropped: a correlation-crowding haircut ("P4c" — no measurable effect); running
the vol-target scalar without the caps (blows out to −35% in the 2022 drawdown).

### Recorded results (descriptive, survivorship-inflated — do not quote as fact)

| Portfolio P4, full universe | normal cost | cost ×2 |
| --- | --- | --- |
| `k_max = 1` (headline) | CAGR 26.1%, vol 7.1%, Sharpe 3.30, maxDD −9.2%, Calmar 2.83 | CAGR 23.7%, Sharpe 3.03, maxDD −9.8%, Calmar 2.43 |
| `k_max = 2` (alt) | CAGR 38.4%, vol 9.4%, Sharpe 3.50, maxDD −10.4%, Calmar 3.68 | CAGR 34.7%, Sharpe 3.21, maxDD −11.0%, Calmar 3.14 |
| Benchmarks (same window) | SPY CAGR 12.5% / Sharpe 0.83 / maxDD −33.8% · 60/40 CAGR 8.2% / Sharpe 0.85 / maxDD −21.9% | — |

Sharpe 3+ / maxDD −9% is not a real trend benchmark; it is what survivorship
bias plus diversification of a winner-heavy book produces.

### V1 rules

1. **No parameter optimisation inside V1** — a different parameter set is a new
   strategy (V3, V4…), added as a new `signal_strategies` row.
2. Future models report incremental value **relative to this benchmark**, on the
   same universe / window / cost assumptions.
3. If a point-in-time or non-equity-heavy universe becomes available, the
   *direction* default in particular could move toward long/short — the
   drift-quintile evidence (below) shows the short side is only weak because the
   universe is mostly winners.

---

## How each decision was reached (one paragraph each — the "why", hardcoded)

**Stage 1 — entry horizon → Fast 20/10, Bond ETFs 100/50.** Across the full
universe, ranking the four horizons {20/10, 40/20, 55/20, 100/50} by each
symbol's historical Sharpe, **Fast 20/10 was the per-symbol winner for 386 of
660** symbols (58.5%; 56.5% at ×2 cost) — a clear plurality. The exceptions:
**Bond ETFs favoured Slow 100/50, 10 of 17** (bond trends are slower; the fast
break whipsaws), and broad-index ETFs favoured Fast 14 of 15. Bitcoin on Fast
over its available history: CAGR 27.70%, Sharpe 1.01, maxDD −24.82%.

**Stage 2 — exit architecture → `c3_d20` (Chandelier 3×ATR trail + Donchian-20
reversal backstop + initial 2×ATR stop), no exception.** Holding the entry
cluster fixed and sweeping the Donchian reversal-channel width against the
Chandelier trail, the **decorated** exit (a wide 20–100-day structure backstop)
beat the **plain tight** one (`c3_d10`, the pre-V1 default) by **+0.17 median
Sharpe on every sleeve**. Among the wide variants, `c3_d20` was the modal
per-symbol Sharpe winner (**37%** full universe; 41% watchlist; 47% bonds) with
the best medians (full-universe median Sharpe 0.80 vs 0.76 for the pure Donchian
channel and 0.73 for `c3_d10`). The looser `c4_d10` and the pure channel are
dropped. Bonds are backstop-insensitive, so no bond exit exception.

**Stage 3 — direction → long only, with Bond ETFs and Bitcoin as long/short
exceptions.** At the frozen exit, adding the short side (`both` minus `long`)
cost **−0.24 median Sharpe** across the full universe with ≈ 0 CAGR gain — but
the *standalone* short leg has a **positive median Sharpe (+0.13, profitable for
72% of names)**, so the short entry rule is not broken; combining it with a
strongly drifting long book just adds volatility. The de-bias control confirms
this: splitting the equity universe by each symbol's own buy-&-hold drift, the
short side is **Sharpe-neutral (−0.05) and +4.1pp CAGR on the flat/declining
quintile** and only becomes a −0.32 Sharpe drag on the strong-uptrend quintile.
So long-only wins **for this winner-heavy universe**, not universally. The two
keepers: **Bond ETFs** (ΔSharpe −0.06, standalone short Sharpe +0.33 — pays
through rate-hike bear legs) and **Bitcoin** (ΔCAGR +6.5% at ΔSharpe −0.06,
standalone short Sharpe +0.41 — the 2022 crypto crash was very shortable). ETH
stays long only (its combined drawdown blows out −24%). The "illiquid small caps
are two-sided" hypothesis was tested and **not supported** — dollar-volume
quintiles are flat; the real (continuous, non-cluster) axis is volatility.

**Stage 4 — portfolio → rule P4; the position/gross caps are the whole
risk layer.** Walking a rule ladder (equal-weight → inverse-vol → + vol-target
scalar → + caps → + sleeve budgets → + correlation haircut): inverse-vol halves
CAGR by removing the "lean into the volatile winners" bias; the **caps** take
max drawdown from −18.7% to −9.2% (2022: −18.7% → −9.2%) and are non-negotiable;
sleeve budgets add ~2pp CAGR and a declared cross-asset rule; the **correlation
haircut changed nothing and was dropped**. The vol-target scalar *without* caps
is actively dangerous under leverage (2022 drawdown −35%). Robustness grid: not
knife-edge on lookback, vol target, or position cap; daily rebalancing is
clearly worse than weekly.

**Stage 5 — cost ×2 sanity check → all four decisions survived.** Every stage
script re-run at doubled `cost_bps` and `slippage_atr`: entry still Fast-plurality
with bonds still Slow; exit still `c3_d20` (modal, best median); direction
keep-list still exactly {Bond ETF, Bitcoin}; portfolio ladder ranking identical
(Calmar down ~15–20%). The extra cost penalises turnover exactly where expected
without moving any cluster boundary.

---

## As-built (migration `0014`)

- **`signal_strategies`** registry — `(id, key, name, params_json, is_default,
  note, …)`. Seeded with `naive-donchian-v1` (default) and
  `naive-donchian-v1-slow-entry`. Immutable rows; a new parameter set is a new
  row.
- **`assets.strategy_id` / `crypto_assets.strategy_id`** — explicit on every
  active row (default → V1, the `ETF_BONDS` set → slow). Dormant rows are NULL
  and fall back to the default. **`signal_symbol_stats`** gains `strategy_id`;
  its `params_json` already records the exact per-symbol params of each run.
- **`signal_config`** and `GET`/`PUT /api/signals/config` are untouched —
  vestigial fallback, no longer read for the board.
- The universe run resolves `symbol → params` from the registry and runs each
  symbol with its own strategy; direction is still forced two-sided for every
  symbol.
- API: `GET /api/signals/strategies`, `GET /strategies/{id}`,
  `POST /strategies/{id}/assign {symbols:[…]}`,
  `GET /strategies/resolve/{symbol}`, and `POST /preview {symbol, params}` — a
  stateless single-symbol run that persists nothing.
- **Strategies page** (`/strategies`) — list, param diff vs default, `note`,
  assigned symbols, an "Apply to…" assignment control.
- **Timing page** — no "Save"; the form pre-fills from the resolved strategy and
  **Run** calls `/preview`. The board keeps the last stored (universe-run)
  signals until the next Trend run.
- **Trend page** — the Watchlist header expands a static "Position allocation
  (advisory)" note (the P4 idea in plain language). No portfolio engine.

Full design + the fuller un-built plan: `docs/design-v2/08-strategy-management.md`.
