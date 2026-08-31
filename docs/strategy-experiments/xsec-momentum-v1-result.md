# Cross-sectional momentum V1 — result

Frozen conclusions of the momentum research: the reference for a future
"relative-strength" strategy version. Results and guidance only — not the
process. Do not delete; add a sibling file for a new model.

## Archived — do not reproduce

The full experiment code and raw outputs (`backend/temp/momentum_*.py`,
`docs/temp/momentum_m*`) were committed once at **`0d5e72c`** then removed
from the working tree in the next commit. Every number in this file is a
literal — nothing depends on those outputs. **Do not fetch git history to
"verify" or "reproduce".** The user does not care about reproduction fidelity —
it wastes tokens and context.

All figures are descriptive and **survivorship-inflated** — the universe is the
676 symbols in `assets.active` today (≈ current S&P 500 / NDX / sector-SPDR
membership), so a 2016-start backtest is selecting on known winners. Sharpe
1.6–3.0 and CAGR 40–90 % are **not real**. Only two things are trustworthy: the
*ranking* of the rules (it held across sub-periods and a cost-×2 check), and the
*gap* between a long book and its short leg.

## Frozen spec

Walk-forward event backtest, 2016-01-04 → 2026-08-28, 676 active
equities/ETFs, SPY session calendar. Cost 5 bps per unit of turnover. No
point-in-time membership.

### Selection (Stage M1)

- **Signal** — the Multisectional page's composite score, recomputed as of each
  rebalance from each symbol's truncated series: universe-percentile-rank then
  weighted mean of `rs_3m .25 / rs_6m .25 / rs_12m .15` (own 63/126/252-session
  return minus SPY's), `high_52w_distance .15`, `trend_distance .10`
  (mean `ln(price/SMA_n)`, n ∈ 20/50/100/200), `slope .10` (SMA_50/SMA_200
  rising).
- **Basket** — top **N = 20** by composite, equal weight before sizing.
- **Cadence** — **monthly** rebalance (first session of each month).
- **Skip-recent** — **none** (no Jegadeesh-Titman 12-1 gap; `rs_*` already
  blends horizons and the explicit skip hurt in every cell).

### Exit (Stage M2) — `E2`

1. **Hysteresis band** — an incumbent is kept while its rank stays within
   `1.5 · N` (top 30); it is only replaced once it falls past 30. Refill to 20
   with the highest-ranked non-held names. (Lower turnover; on its own it does
   nothing — see the table.)
2. **Per-name trend gate** — checked daily: a held name that closes below its
   own `SMA_100` is exited at once; the freed weight sits in **cash** until the
   next monthly rebalance, which is the only re-entry path.

No asset-class exception (the book is equities/ETFs only).

### Direction (Stage M3)

**Long only. No exception.** Every de-biased slice — full universe, drift
quintiles, sub-periods — says the short leg only adds drawdown. (Contrast the
Donchian V1, where Bond ETFs and BTC earned a two-sided exception; momentum has
no such sleeve.)

### Sizing (Stage M4) — the Turtle P4 ladder, headline `k_max = 1`

1. **Inverse-vol** — `w_i ∝ 1 / σ_i`, σ = annualised stdev of the trailing
   60 daily returns, normalised across the held names.
2. **Vol-target scalar** — multiply the book by
   `clip(0.12 / trailing_20d_annualised_port_vol, 0, 1)` — **de-lever only**,
   never above 1×. This is the layer that matters.
3. **Caps** — per-name `w_i ≤ 10 %` of NAV; one GICS **sector ≤ 30 %** of gross
   (momentum-crowding guard). Trimmed weight → cash.

Dropped: the Barroso crash-de-risk scalar (`S5`) — no measurable gain over the
sector cap.

## The four stage tables

Every number is a literal. Universe = 676 active symbols. "at ×2" = the same
run with `cost_bps` doubled to 10 (Stage M5). Benchmarks over the same window:
**SPY buy&hold** CAGR 15.3 % / Sharpe 0.88 / maxDD −33.8 %; **equal-weight
universe** CAGR 18.2 % / Sharpe 1.00 / maxDD −36.7 %.

### Stage M1 — Selection → **composite score, N = 20, monthly, skip = 0**

| N | Cadence | Skip | CAGR | Vol | Sharpe | max DD | Calmar | Turnover/yr |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | weekly | 0 | 192.5 % | 32.8 % | 3.44 | −26.2 % | 7.36 | 52 |
| 20 | weekly | 0 | 121.9 % | 27.5 % | 3.04 | −24.0 % | 5.09 | 52 |
| 40 | weekly | 0 | 76.3 % | 23.7 % | 2.51 | −23.5 % | 3.25 | 52 |
| 10 | monthly | 0 | 67.7 % | 32.8 % | 1.74 | −33.0 % | 2.05 | 12 |
| **20** | **monthly** | **0** | **52.7 %** | **28.5 %** | **1.63** | **−30.0 %** | **1.76** | **12** |
| 40 | monthly | 0 | 42.3 % | 25.3 % | 1.52 | −30.5 % | 1.39 | 12 |
| 20 | monthly | 21 | 46.1 % | 29.3 % | 1.44 | −31.9 % | 1.45 | 12 |
| 20 | quarterly | 0 | 38.2 % | 30.0 % | 1.23 | −40.2 % | 0.95 | 4 |

Weekly has the highest Sharpe but it is the **overfit trap** — 52× annual
turnover, "always hold last week's hottest name" on a winners-only universe.
Quarterly gives up too much (maxDD −40 %, Calmar < 1). `skip = 21` lowered
Sharpe in **every** cell. Monthly N = 20 beats the equal-weight universe on both
return and drawdown in all three sub-periods (2016-19 / 2020-22 / 2023-present).

### Stage M2 — Exit → **`E2`** (hysteresis band + per-name SMA_100 trend gate → cash)

M1 fixed. Full period.

| Variant | CAGR | Sharpe | max DD | Calmar | Turnover/yr | Avg gross | Avg hold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `E0` rank-only | 52.7 % | 1.63 | −30.0 % | 1.76 | 14.8 | 100 % | 34 d |
| `E1` hysteresis only | 51.7 % | 1.58 | −31.1 % | 1.67 | 12.0 | 100 % | 42 d |
| **`E2` + SMA_100 gate** | **57.5 %** | **1.86** | **−21.6 %** | **2.66** | **12.3** | **95 %** | **39 d** |
| `E3` + own-21d-return gate | 69.7 % | 2.84 | −12.9 % | 5.39 | 16.9 | 66 % | 20 d |
| `E4` + Chandelier 3×ATR trail | 82.3 % | 3.02 | −13.6 % | 6.03 | 14.7 | 79 % | 27 d |

`E2` by sub-period: Sharpe **1.91 / 1.51 / 2.18**, maxDD **−16.4 % / −20.8 % /
−21.6 %** (2016-19 / 2020-22 / 2023-present) — stable.

**Hysteresis on its own does nothing** (`E1 ≈ E0`, just lower turnover) — the
cross-sectional rank is already a relative backstop, unlike the Donchian's
`c3_d20`. **The SMA_100 gate is the clean win**: one explainable rule, 5 %
average cash drag, maxDD −30 % → −22 %, and it *adds* return. `E3` / `E4` post
better numbers only by parking **20–34 % in cash on average** — that is a
market-exposure throttle, not an exit, and a survivorship universe massively
rewards "bail on any wobble, buy back next month". **`E4` is noted as a V2
candidate; it is not in V1.**

### Stage M3 — Direction → **long only, no exception**

M1 + M2 fixed. `long_short` is dollar-neutral (gross ≈ 2.0; CAGR/vol scale with
it, Sharpe does not). `short` = the loser basket run standalone.

| Direction | CAGR | Sharpe | max DD | Calmar | Avg gross |
| --- | ---: | ---: | ---: | ---: | ---: |
| **long** | **57.5 %** | **1.86** | **−21.6 %** | **2.66** | 95 % |
| long_short | 45.0 % | 1.13 | **−57.8 %** | 0.78 | 183 % |
| short (standalone) | **−9.1 %** | **−0.11** | **−76.8 %** | −0.12 | 88 % |

Adding the short leg roughly **halves Sharpe and triples max drawdown**.
Shorting momentum losers *loses money* with a −77 % tail — the Daniel-Moskowitz
"momentum crash" signature (the short leg blows up in sharp reversals: 2020-04,
2022).

De-bias control — universe split into quintiles by each symbol's own full-sample
buy&hold drift (Q1 weakest, Q5 strongest), long book re-run inside each:

| Drift quintile | long Sharpe | long CAGR | long max DD | short Sharpe |
| --- | ---: | ---: | ---: | ---: |
| Q1 | **1.44** | 22.8 % | −14.9 % | +0.26 |
| Q2 | 1.58 | 22.0 % | −9.8 % | −0.08 |
| Q3 | 1.60 | 23.8 % | −10.2 % | −0.18 |
| Q4 | 1.83 | 34.0 % | −13.4 % | −0.20 |
| Q5 | 1.98 | 64.0 % | −27.6 % | −0.26 |

The long edge is **positive and strong in every quintile**, including the
weakest-drift names — so it is momentum, not just "own the winners". The short
leg is negative-to-flat everywhere with −55 % to −68 % drawdowns. Dead.

### Stage M4 — Sizing → inverse-vol + 12 % vol-target (de-lever) + 10 % name / 30 % sector caps

M1 + M2 + M3 fixed. `k_max = 1` (never levers up). Each row adds one layer.
"DD 2020" / "DD 2022" = drawdown inside those windows.

| Variant | CAGR | Vol | Sharpe | max DD | Calmar | Avg gross | DD 2020 | DD 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `S0` equal weight | 57.5 % | 26.4 % | 1.86 | −21.6 % | 2.66 | 95 % | −16.9 % | −20.8 % |
| `S1` inverse-vol | 50.5 % | 24.2 % | 1.81 | −19.3 % | 2.61 | 95 % | −14.4 % | −19.3 % |
| `S2` + vol-target (de-lever) | 40.9 % | 18.2 % | 1.97 | −14.6 % | 2.80 | 75 % | −9.8 % | −11.2 % |
| `S3` + 10 % name / 100 % gross caps | 41.0 % | 18.2 % | 1.98 | −14.5 % | 2.83 | 75 % | −9.8 % | −11.2 % |
| **`S4` + 30 % sector cap** | **40.5 %** | **17.4 %** | **2.04** | **−14.0 %** | **2.89** | 74 % | **−8.5 %** | **−10.3 %** |
| `S5` + Barroso crash de-risk | 39.9 % | 17.7 % | 1.99 | −14.1 % | 2.84 | 73 % | −9.4 % | −11.0 % |

The decisive layer is **`S1 → S2`** (the 12 % vol-target de-lever) — it halves
the 2020 and 2022 drawdowns and trims the inflated CAGR (fine — the CAGR is
survivorship anyway). The **sector cap** (`S3 → S4`) is a small, clean
improvement that directly targets momentum's habit of crowding into one sector.
The crash-de-risk scalar (`S5`) adds nothing on top — dropped.

### Stage M5 — Cost ×2 sanity check → every decision survives

| Stage | 1× decision | at 2× cost | Survives? |
| --- | --- | --- | --- |
| **M1 Selection** | composite, N = 20, monthly, skip = 0 | ordering identical; monthly N = 20 Sharpe 1.63 → 1.61 | **Yes** |
| **M2 Exit** | `E2`; hysteresis alone ≈ `E0` | `E2` Sharpe 1.86 → 1.83, maxDD −21.6 % → −21.7 % | **Yes** |
| **M3 Direction** | long only, no exception | long Sharpe 1.86 → 1.83; short still −0.13 / −77.5 %; every quintile's long leg still ≥ 1.4 | **Yes** |
| **M4 Sizing** | `S4` (vol-target + caps + sector cap) | `S4` Sharpe 2.04 → 2.01, Calmar 2.89 → 2.82, DD 2020 −8.5 % → −8.6 % | **Yes** |

Turnover is 12–17×/yr, so doubling 5 bps → 10 bps costs ≈ 0.1 %/yr. Nothing
moves.

## V1 rules

1. **No parameter optimisation inside V1** — a different N, cadence, gate, or
   metric weight is a new strategy (V2…), a new `signal_strategies` row.
2. Future models report incremental value **relative to this benchmark**, on the
   same universe / window / cost assumptions.
3. On a point-in-time or non-equity universe, re-run Stage M3 — the long-only
   verdict leans on this universe being mostly winners (drift-quintile table).
4. `E4` (Chandelier trail) and a lighter exposure throttle are the sanctioned
   directions for a V2.

## As-built

**Not wired into the app.** Unlike the Donchian V1, this is research only —
there is no `signal_strategies` row, no runner path, no page.

To ship it, the runner needs a **portfolio-level path** (rank the whole universe
each rebalance, hold a 20-name basket with the `E2` gate and the P4 sizing) —
distinct from the per-symbol Donchian engine. When that is built:

- a new `signal_strategies` key `xsec-momentum-v1` with the spec above in
  `params_json` (`model: "xsec_momentum"`), `is_default = 0`;
- assignment stays per-symbol via `assets.strategy_id`, but the engine reads the
  whole assigned set as one book, not symbol-by-symbol;
- the Multisectional page is the natural home for the board; it stays untouched
  until then.

The Multisectional composite score + leadership persistence already in the app
(`features/multisectional/ranking.py`) are the entry ranking this strategy would
consume — no new indicator work.
