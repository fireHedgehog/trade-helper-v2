# Naive Donchian V1 — result

Frozen conclusions of the strategy research: the single reference for the app's
first strategy version. Results and guidance only — not the process. Do not
delete; add a sibling file for a new model.

## Archived — do not reproduce

The full experiment code and raw outputs (`backend/temp/`, `docs/temp/`) were
committed once at **`c296945`** then removed
(`https://github.com/fireHedgehog/trade-helper-v2/tree/c296945`). Every number
in this file is a literal — nothing depends on those outputs. **Do not fetch
git history to "verify" or "reproduce".** The user does not care about
reproduction fidelity — it wastes tokens and context.

All figures are descriptive and **survivorship-inflated** (universe = today's
index membership; no point-in-time data). Only the *ranking* of the rules is
trustworthy — it held across two cost levels, two universe definitions, and a
robustness grid.

## Frozen spec

Engine `donchian-1`. Data 2016-01-04 → 2026-08-30. Universe = active
equities/ETFs ∪ active crypto ∪ `TREND_WATCHLIST` (~678 targets, 673 with ≥ 200
bars).

### Signal — two strategies, differing in `entry_len` only

The engine has one `exit_len` field; under `c3_d20` it is the Donchian-20
reversal-backstop width. "100/50" was Turtle notation, not a second field.

| Knob | `naive-donchian-v1` (default) | `naive-donchian-v1-slow-entry` (Bond ETFs) |
| --- | --- | --- |
| `entry_len` | **20** | **100** |
| `exit_len` | 20 | 20 |
| `trail_mode` / `chandelier_k` | `chandelier` / 3.0 | same |
| `atr_stop_mult` / `atr_len` | 2.0 / 20 | same |
| `fill_at` | `open_next` | same |
| `cost_bps` / `slippage_atr` | 5.0 / 0.05 | same |
| `use_ma_regime` / `stop_and_reverse` | off | same |
| `allow_short` | false (advisory) | true (bonds); advisory-true for `BTC/USD` on the default |

Default `params_json`:
`{"model":"donchian","entry_len":20,"exit_len":20,"atr_len":20,"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,"warmup_buffer":10,"allow_long":true,"allow_short":false}` —
bond variant is the same with `entry_len:100`.

Direction is **not** a board filter: the universe run always computes long *and*
short for every symbol. The recommendation (long only; Bond ETFs + `BTC/USD`
two-sided; ETH long only) is UI text, so a future short-capable strategy needs
no re-fetch.

### Portfolio — rule P4 (advisory text only, no code)

1. Inverse-vol sizing — `w_i ∝ 1 / σ_i` (60-day annualised σ), gross normalised
   to 100% across on-signals.
2. Vol-target scalar — multiply the book by `clip(0.12 / trailing_60d_vol, 0, k_max)`.
3. Caps — per-position `|w_i| ≤ 10%` of NAV; gross `≤ k_max`.
4. Fixed sleeve risk budgets — equity 0.50 / bond 0.20 / commodity 0.15 /
   crypto 0.05 / other 0.10; inverse-vol within a sleeve; inactive sleeves'
   budget redistributed pro-rata.
5. Weekly rebalance. Headline `k_max = 1` (unlevered); `k_max = 2` documented alt.

Dropped: correlation-crowding haircut (no measurable effect); the vol-target
scalar without the caps (−35% in the 2022 drawdown).

### Recorded results (descriptive — do not quote as fact)

| P4, full universe | normal cost | cost ×2 |
| --- | --- | --- |
| `k_max = 1` (headline) | CAGR 26.1%, vol 7.1%, Sharpe 3.30, maxDD −9.2%, Calmar 2.83 | CAGR 23.7%, Sharpe 3.03, maxDD −9.8%, Calmar 2.43 |
| `k_max = 2` (alt) | CAGR 38.4%, vol 9.4%, Sharpe 3.50, maxDD −10.4%, Calmar 3.68 | CAGR 34.7%, Sharpe 3.21, maxDD −11.0%, Calmar 3.14 |
| Benchmarks | SPY CAGR 12.5% / Sharpe 0.83 / maxDD −33.8% · 60/40 CAGR 8.2% / Sharpe 0.85 / maxDD −21.9% | — |

Sharpe 3+ / maxDD −9% is not a real trend benchmark; it is survivorship bias
plus diversification of a winner-heavy book.

## The five stage tables

Every number is a literal in this file. Primary cohort = 660 symbols with ≥ 756
bars unless noted. "at ×2" = same measurement with `cost_bps` and `slippage_atr`
doubled (Stage 5).

### Stage 1 — Entry horizon → **Fast 20/10**, Bond ETFs **100/50**

Per-symbol historical-Sharpe winner among the four horizons, full universe,
long/short.

| Horizon | Winner count | Winner share | Winner share at ×2 |
| --- | ---: | ---: | ---: |
| **Fast 20/10** | **386 / 660** | **58.5%** | **56.5%** |
| Medium 40/20 | 140 / 660 | 21.2% | 21.5% |
| Classic 55/20 | 64 / 660 | 9.7% | 10.5% |
| Slow 100/50 | 70 / 660 | 10.6% | 11.5% |

Exceptions: Bond ETFs favour Slow 100/50, **10 of 17**; broad-index ETFs favour
Fast, **14 of 15**. Bitcoin on Fast, full history: CAGR 27.70%, Sharpe 1.01,
max drawdown −24.82%.

### Stage 2 — Exit → **`c3_d20`** (Chandelier 3×ATR trail + Donchian-20 reversal backstop + initial 2×ATR stop), no exception

Full-universe median, long/short, entry cluster fixed.

| Variant | Median Sharpe | Median CAGR | Median max DD | Median Calmar | Per-symbol Sharpe-winner share |
| --- | ---: | ---: | ---: | ---: | ---: |
| **`c3_d20`** (chosen) | **0.80** | 15.2% | −29.4% | 0.54 | **37.0%** |
| `c3_d100` | 0.77 | 14.5% | −29.0% | 0.52 | 19.1% |
| `channel` (pure Turtle) | 0.76 | 15.1% | −32.4% | 0.48 | 32.9% |
| `c3_d55` | 0.78 | 14.6% | −29.2% | 0.54 | 8.5% |
| `c3_d10` (pre-V1 default) | 0.73 | 13.3% | −30.4% | 0.46 | 2.4% |
| `c4_d10` (looser trail) | 0.49 | 8.5% | −39.0% | 0.23 | 0.2% |

Plain tight backstop (`c3_d10`) vs decorated wide backstop, full-universe median
Sharpe: **0.61 → 0.78** — decorated wins on every sleeve by +0.17 to +0.27. At
×2: `c3_d20` still modal (36% full universe, 41% watchlist, 47% bonds), best
median Sharpe 0.75. `c4_d10` and the pure channel are dropped; bonds are
backstop-insensitive, so no bond exit exception.

### Stage 3 — Direction → **long only**, with **Bond ETFs** and **Bitcoin** as long/short exceptions

Δ = (long/short) − (long only), at the frozen `c3_d20` exit. "short-only Sharpe"
= the short leg run standalone.

| Scope | n | ΔCAGR | ΔSharpe | ΔDD-reduction | short-only Sharpe | % short +ve standalone | Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full universe | 660 | +0.5% | **−0.24** | −10.5% | +0.14 | 72% | long only |
| Individual equity | 556 | +0.4% | −0.24 | −11.7% | +0.13 | 71% | long only |
| Broad index ETF | 15 | +0.3% | −0.36 | −5.3% | +0.07 | 80% | long only |
| Factor/style ETF | 13 | −1.0% | −0.57 | −6.0% | −0.01 | 46% | long only |
| Sector ETF | 11 | −0.8% | −0.43 | −8.4% | +0.02 | 64% | long only |
| Thematic/industry ETF | 36 | +3.1% | −0.14 | −8.1% | +0.28 | 69% | borderline → long only |
| Commodity ETF | 10 | +1.5% | −0.20 | −10.5% | +0.22 | 100% | borderline → long only |
| **Bond ETF** | 17 | +0.8% | **−0.06** | −0.9% | **+0.33** | 82% | **long/short** |
| **Bitcoin** | 1 | **+6.5%** | **−0.06** | −4.0% | **+0.41** | 100% | **long/short** |
| Crypto (ETH) | 1 | +1.8% | −0.28 | −24.1% | +0.31 | 100% | long only |

De-bias control — Individual equities by each symbol's own buy-&-hold drift. The
short-side drag rises monotonically with drift, so long-only wins **because this
universe is mostly winners**, not universally.

| Drift quintile | median B&H CAGR | ΔCAGR | ΔSharpe | short-only Sharpe |
| --- | ---: | ---: | ---: | ---: |
| Q1 (−32%…6%, flat / declining) | 2.2% | **+4.1%** | **−0.05** | +0.32 |
| Q2 (6…11%) | 8.8% | +1.2% | −0.17 | +0.17 |
| Q3 (11…15%) | 12.9% | −0.2% | −0.24 | +0.10 |
| Q4 (15…21%) | 17.1% | −0.5% | −0.30 | +0.08 |
| Q5 (21…93%, strong uptrend) | 27.8% | −1.3% | −0.32 | +0.04 |

"Illiquid small caps are two-sided" was tested and **not supported** —
dollar-volume quintiles are flat; the real (continuous, non-cluster) axis is
volatility. At ×2: keep-list still exactly {Bond ETF, Bitcoin}; full-universe
ΔSharpe −0.24 → −0.25; standalone short still positive (+0.10 universe, +0.29
bonds, +0.39 BTC).

### Stage 4 — Portfolio → **rule P4**; the position/gross caps are the whole risk layer

Rule ladder, full universe, `k_max = 1` (unlevered) / `k_max = 2` (moderate),
normal cost. Each variant adds one layer.

| Variant | CAGR (k1 / k2) | Vol | max DD (k1 / k2) | Sharpe (k1 / k2) | Calmar (k1 / k2) | 2020 COVID DD | 2022 DD |
| --- | --- | ---: | --- | --- | --- | ---: | ---: |
| P0 equal-notional | 36.9% / 36.9% | 11.9% | −18.7% / −18.7% | 2.71 / 2.71 | 1.97 / 1.97 | −7.6% | −18.7% |
| P1 inverse-vol | 17.2% / 17.2% | 8.9% | −18.7% / −18.7% | 1.82 / 1.82 | 0.92 / 0.92 | −9.0% | −18.7% |
| P2 + vol-target scalar | 15.7% / 21.0% | 8.3 / 13.6% | −18.7% / **−35.0%** | 1.81 / 1.47 | 0.84 / 0.60 | −8.7 / −15.3% | −18.7 / −35.0% |
| **P3 + caps** | 23.9% / 35.7% | 7.0 / 9.5% | **−9.2% / −10.3%** | 3.08 / 3.27 | 2.60 / 3.48 | −3.6% | −9.2% |
| **P4 + sleeve budgets** | 26.1% / 38.4% | 7.1 / 9.4% | −9.2% / −10.4% | 3.30 / 3.50 | 2.83 / 3.68 | −3.1% | −9.2% |
| P4c + corr haircut | 25.7% / 38.7% | 6.9 / 9.3% | −9.3% / −10.7% | 3.34 / 3.56 | 2.76 / 3.63 | −3.1% | −9.3% |

Benchmarks, same window: SPY CAGR 12.5% / Sharpe 0.83 / maxDD −33.8% / Calmar
0.37; 60/40 SPY-AGG CAGR 8.2% / Sharpe 0.85 / maxDD −21.9% / Calmar 0.38.

Inverse-vol (P0→P1) halves CAGR by dropping the "lean into the volatile winners"
bias. The **caps (P2→P3)** take max drawdown −18.7% → −9.2% — non-negotiable.
Sleeve budgets (P3→P4) add ~2pp CAGR and a declared cross-asset rule. The
correlation haircut (P4→P4c) changed nothing — dropped. The vol-target scalar
without the caps is dangerous under leverage (2022 −35%). At ×2: ladder ranking
identical, P4 Calmar 2.83 → 2.43 (k1) and 3.68 → 3.14 (k2); daily rebalancing
craters (Calmar 2.31 → 1.49) — confirms weekly.

### Stage 5 — Cost ×2 sanity check → all four decisions survived

| Stage | 1× decision | at 2× cost | Survives? |
| --- | --- | --- | --- |
| **1 Entry** | Fast 20/10 (58.5% winner share); Bond ETFs Slow 100/50 | Fast 56.5%; Bond ETF Slow 10/17; Broad index Fast 14/15 — identical | **Yes** |
| **2 Exit** | `c3_d20`, no exception; decorated beats plain by ~0.18 Sharpe | `c3_d20` still modal (36% / 41% watchlist / 47% bonds), best median Sharpe 0.75 | **Yes** |
| **3 Direction** | long only; long/short for {Bond ETF, Bitcoin} | keep-list unchanged; full-universe ΔSharpe −0.24 → −0.25; standalone short still +ve | **Yes** |
| **4 Portfolio** | P4 (P3 caps critical); P4c dropped; weekly rebalance | Ladder ranking identical; P4 Calmar 2.83 → 2.43 (k1), 3.68 → 3.14 (k2); daily rebalance craters | **Yes** |

## V1 rules

1. **No parameter optimisation inside V1** — a different parameter set is a new
   strategy (V3, V4…), a new `signal_strategies` row.
2. Future models report incremental value **relative to this benchmark**, on the
   same universe / window / cost assumptions.
3. On a point-in-time or non-equity-heavy universe, re-run Stage 3 — the
   direction default could move toward long/short (drift-quintile table).

## As-built (migration `0014`)

- **`signal_strategies`** — `(id, key, name, params_json, is_default, note, …)`,
  seeded with the two strategies above. Immutable rows.
- **`assets.strategy_id` / `crypto_assets.strategy_id`** — explicit on every
  active row (default → V1, `ETF_BONDS` → slow); NULL rows fall back to the
  default. **`signal_symbol_stats`** gains `strategy_id`.
- **`signal_config`** + `GET`/`PUT /api/signals/config` — untouched, vestigial
  fallback, not read for the board.
- Universe run resolves `symbol → params` from the registry; direction still
  forced two-sided for every symbol.
- API: `GET /api/signals/strategies`, `GET /strategies/{id}`,
  `POST /strategies/{id}/assign {symbols:[…]}`,
  `GET /strategies/resolve/{symbol}`, stateless `POST /preview {symbol, params}`.
- **Strategies page** (`/strategies`) — list, param diff vs default, `note`,
  assigned symbols, "Apply to…" assignment.
- **Timing page** — no Save; form pre-fills from the resolved strategy, **Run**
  calls `/preview` (persists nothing).
- **Trend page** — the Watchlist header expands a static "Position allocation
  (advisory)" note.

Full design + the fuller un-built plan: `docs/design-v2/08-strategy-management.md`.
