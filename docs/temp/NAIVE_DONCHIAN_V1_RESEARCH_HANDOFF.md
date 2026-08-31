# Naive Donchian V1 Research Handoff

Status: **FROZEN - all five stages complete and user-signed-off; the cost-x2
sanity check passed on every decision. The benchmark is `Naive Donchian V1`
(spec below). No further parameter optimisation is permitted inside V1.**

Method note: each stage was its own sequential experiment producing one
`default + exception` rule. Exit and direction were NOT run together - short-side
value interacts with exit behaviour, so the direction table was sliced at the
already-frozen exit.

## FROZEN: Naive Donchian V1 Benchmark

### Per-symbol signal (deterministic; engine `donchian-1`)

The engine has one `exit_len` field; under the `c3_d20` exit it is the
Donchian-20 reversal backstop width. So **the only knob that differs between
the default and the bond exception is `entry_len` (20 vs 100)** - "100/50" was
Turtle notation, it does not map to a second engine field here.

| Knob | Default (strategy "V1") | Bond-ETF exception (strategy "V2") |
| --- | --- | --- |
| `entry_len` | **20** | **100** |
| `exit_len` | 20 | 20 |
| `trail_mode` / `chandelier_k` | `chandelier` / 3.0 | same |
| `atr_stop_mult` / `atr_len` | 2.0 / 20 | same |
| `fill_at` | `open_next` | same |
| `cost_bps` / `slippage_atr` | 5.0 / 0.05 (daily path books the bps, not the ATR slippage) | same |
| `use_ma_regime` / `stop_and_reverse` | off | same |
| Direction (`allow_short`) | long only (`false`) *(see note)* | long/short (`true`) for Bond ETFs; also `true` for `BTC/USD` on V1 |

Exact V1 `params_json`:
`{"model":"donchian","entry_len":20,"exit_len":20,"atr_len":20,"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,"warmup_buffer":10,"allow_long":true,"allow_short":false}`
V2 = V1 with `entry_len:100`.

Direction note: the **Trend board still runs long/short for every symbol** (the
engine already forces `allow_long=allow_short=true` for the universe run). The
per-class `allow_short` above is a *recommendation* to surface in the UI (Bond
ETFs + `BTC/USD`), not a board filter. ETH/USD stays long-only-recommended.
"Bond ETFs" = the `ETF_BONDS` set.

### Portfolio construction (rule **P4**)

1. **Inverse-vol position sizing**: `w_i` proportional to `1 / sigma_i`,
   `sigma_i` = 60-trading-day annualised stdev of the instrument's underlying
   return, lagged one day; gross normalised to 100% across the on-signals.
2. **Portfolio vol-target scalar**: multiply the book by
   `k(t) = clip(0.12 / trailing_60d_portfolio_vol, 0, k_max)`.
3. **Caps**: per-position `|w_i| <= 10%` of NAV (excess handed back to uncapped
   names); gross `<= k_max`.
4. **Fixed sleeve risk budgets**: equity 0.50 / bond 0.20 / commodity 0.15 /
   crypto 0.05 / other 0.10; inverse-vol within sleeve; inactive sleeves'
   budget redistributed pro-rata. Then apply the scalar and caps.
5. **Weekly rebalance** (first trading day of each ISO week); resizing cost
   `cost_bps * sum|dw_i|` booked on rebalance days.
6. **Leverage**: frozen headline **`k_max = 1`** (unlevered, gross <= 100%);
   **`k_max = 2`** (gross <= 200%) is the documented live-deployment alternative.

Dropped: P4c correlation-crowding haircut (no material effect); running the
vol-target scalar without caps (dangerous under leverage).

### Dataset / universe / provenance

- Engine version `donchian-1`; active config snapshot `Donchian 20/10 (v1)`.
- Price history 2016-01-04 -> 2026-08-30 (adjusted `price_bars` for equities/
  ETFs, raw `crypto_bars` for BTC/ETH). Portfolio window 2016-02-02 -> 2026-08-30.
- Universe = active equities/ETFs UNION active crypto UNION the hard-coded
  `TREND_WATCHLIST`; 678 targets, 673 with >= 200 bars. **Current-membership /
  survivorship biased** - all headline metrics are descriptive, not validated.

### Recorded results (descriptive, survivorship-inflated)

| Portfolio P4, full universe | normal cost | cost x2 |
| --- | --- | --- |
| k_max = 1 (headline) | CAGR 26.1%, vol 7.1%, Sharpe 3.30, maxDD -9.2%, Calmar 2.83 | CAGR 23.7%, vol 7.1%, Sharpe 3.03, maxDD -9.8%, Calmar 2.43 |
| k_max = 2 (alt) | CAGR 38.4%, vol 9.4%, Sharpe 3.50, maxDD -10.4%, Calmar 3.68 | CAGR 34.7%, vol 9.4%, Sharpe 3.21, maxDD -11.0%, Calmar 3.14 |
| Benchmarks (same window) | SPY: CAGR 12.5%, Sharpe 0.83, maxDD -33.8%, Calmar 0.37 &nbsp; / &nbsp; 60/40: CAGR 8.2%, Sharpe 0.85, maxDD -21.9%, Calmar 0.38 | - |

These Sharpe/Calmar levels are not credible in absolute terms (survivorship
bias, no point-in-time universe, diversification of a winner-heavy book). The
usable content is the **rule ladder ranking** and its stability across cost
levels, universes, and the robustness grid.

### V1 rules

1. No further parameter optimisation inside V1 - "edit" means a new model.
2. Future models must report incremental value **relative to this benchmark**,
   on the same universe / window / cost assumptions.
3. Re-run the stages if a point-in-time or non-equity-heavy universe becomes
   available; the direction default especially could move toward long/short
   there (drift-quintile evidence in Stage 3).

## Implementation mapping (decided; NOT built yet)

Small `signal_strategies` registry, migration `0014`. Keep it minimal - keep
`signal_config` and `get_config` as-is (vestigial fallback; never delete seed
rows).

- `signal_strategies(id, key, name, params_json, is_default, note, created_at)`
  seeded with **V1** (`entry_len:20`, frozen params, `is_default=1`) and
  **V2** (V1 with `entry_len:100`).
- `assets.strategy_id` and `crypto_assets.strategy_id` - **explicit id on every
  row** (no NULL-means-default), backfilled: everything -> V1, `ETF_BONDS` -> V2.
  Management page must look professional as V3/V4 appear.
- `signal_symbol_stats` gains a nullable `strategy_id`; its `params_json` column
  already gives per-(run, symbol) provenance.
- `run_universe`: resolve `assets.strategy_id -> params` once at run start, loop
  per symbol. **Direction unchanged** - the board still runs long/short for every
  symbol (keeps the short entry point alive for future short-capable V3+; only
  the Bond ETF short signal is currently trustworthy). `allow_short` in a
  strategy's `params_json` is documentation, not a board filter.
- Timing: **D1** - new stateless `POST /signals/preview {symbol, params}` runs
  the engine and returns the payload, writes nothing. Remove the Save button and
  stop calling `PUT /config` from the frontend (leave the backend route). The
  Timing form pre-fills from the symbol's resolved strategy params.
- Strategy page `/strategies`: list the registered strategies, param diff, a
  `note` text field (e.g. "experiments show bonds gain materially from the short
  side"), an "Apply to" action (writes `strategy_id` for a symbol selection),
  and a table of the symbols currently pointing at each.

### Portfolio: no code

The operator does not trade off this and treats the Stage 4 result as reference
only. **Do not build a portfolio/sizing layer.** Instead: the Trend page
watchlist header becomes collapsible; expanded, it shows a **static advisory
text** ("roughly how you'd allocate" per the always-present long / short / flat
states) - no real position control, no engine. The Stage 4 numbers stay in this
research doc.

This directory is intentionally committed. It contains disposable research code,
raw outputs, and a reproducible handoff snapshot. It is not application runtime
code, but it must remain available across machines until Naive Donchian V1 is
frozen as the canonical trend benchmark.

## Research objective

The objective is not to discover the historically optimal Turtle parameter set.
It is to define a simple, reasonable, explainable, cross-asset canonical trend
model that can serve as a stable benchmark for future models.

Do not continue optimizing small basis-point differences. Do not tune parameters
per symbol. Prefer a small number of economically meaningful asset-class rules.

## Research tree

1. **Entry horizon - COMPLETE** (Fast 20/10 default, Bond ETFs 100/50; signed off)
2. **Exit architecture - COMPLETE** (`c3_d20`, no exception; signed off)
3. **Direction architecture - COMPLETE** (long only; long/short for Bond ETFs + Bitcoin; signed off)
4. **Portfolio aggregation - COMPLETE** (P4, weekly, unlevered headline, P4c dropped; signed off)
5. **Cost x2 sanity check - COMPLETE** (all four decisions survive at 2x cost)
6. **Freeze Naive Donchian V1 - DONE** (spec above)

After the freeze, new research should compare genuinely different models against
this benchmark instead of extracting the last few basis points from the same
Donchian rule.

## Completed entry-horizon decision

Use the following deliberately coarse cluster:

| Asset cluster | Entry horizon | Decision |
| --- | --- | --- |
| Default, including broad indexes, equities, commodities, and Bitcoin | Fast 20/10 | Canonical default |
| Bond ETFs | Slow 100/50 | Asset-class exception |

The full-universe, long/short, full-history Sharpe winners in the primary cohort
were:

| Horizon | Winner count | Winner share |
| --- | ---: | ---: |
| Fast 20/10 | 386 / 660 | 58.5% |
| Medium 40/20 | 140 / 660 | 21.2% |
| Slow 100/50 | 70 / 660 | 10.6% |
| Classic 55/20 | 64 / 660 | 9.7% |

The important exception was Bond ETFs: Slow won 10 of 17 symbols. Broad index
ETFs favored Fast in 14 of 15 symbols. Bitcoin, reported independently while
Ethereum remains in the full universe, favored Fast over the full available history: CAGR 27.70%, Sharpe
1.01, and maximum drawdown -24.82% from 2021-01-01 through 2026-08-30.

This is sufficient evidence for a canonical benchmark decision. It is not a
claim that Fast is universally or permanently optimal.

## Existing snapshot caveat

The committed CSV and HTML outputs are the untouched results from the completed
678-target run. That historical snapshot contains both BTC/USD and ETH/USD under
the original `Crypto` label. The current research script preserves both assets in
the full universe, reports BTC/USD under `Bitcoin` for a clearer standalone
summary, leaves ETH/USD under `Crypto`, and defaults headline selectors to
`Full universe`. A request for a standalone statistic must never change universe
membership.

An attempted rerun after that presentation change was stopped before completion
and before any outputs were written. Do not interpret output timestamps as a
new experiment.

## Stage 2 exit-architecture decision (signed off)

Method: `backend/temp/exit_architecture_experiment.py`. Entry cluster fixed
(Bond ETFs 100/50, else 20/10); direction held at long/short; initial 2 ATR
disaster stop always on. The give-back trail is Chandelier 3 ATR in every
chandelier variant; the swept dimension is the Donchian reversal-channel width.
673 symbols, 4038 engine runs, primary cohort 660 (>= 756 bars).

| Variant | Trailing rule | Donchian reversal backstop |
| --- | --- | --- |
| `channel` | Donchian exit band (Turtle) | width = entry cluster (10 / 50) |
| `c3_d10` | Chandelier 3 ATR | Donchian-10 (tight, ~plain) |
| `c3_d20` | Chandelier 3 ATR | Donchian-20 |
| `c3_d55` | Chandelier 3 ATR | Donchian-55 |
| `c3_d100` | Chandelier 3 ATR | Donchian-100 (~never binds) |
| `c4_d10` | Chandelier 4 ATR | Donchian-10 |

Decision:

| Rule | Value |
| --- | --- |
| **Exit canonical default (whole universe, all asset classes)** | `c3_d20` - Chandelier 3 ATR trailing stop + Donchian-20 reversal backstop + always-on initial 2 ATR disaster stop |
| **Exit asset-class exception** | None. Bonds and BTC both take `c3_d20` cleanly. |

The decorated exit wins - the plain tight version loses on every sleeve. Plain
(`c3_d10`, tight Donchian-10 backstop) vs decorated (wide Donchian-20/55/100
backstop), median over the chandelier variants:

| Scope | Plain Sharpe | Decorated Sharpe | Plain CAGR | Deco CAGR | Plain max DD | Deco max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full universe | 0.61 | 0.78 | 10.8% | 14.7% | -34.3% | -29.2% |
| Watchlist | 0.73 | 0.94 | 11.7% | 14.8% | -25.2% | -19.7% |
| Individual equity | 0.59 | 0.76 | 11.2% | 15.2% | -36.1% | -30.4% |
| Broad index ETF | 0.63 | 0.90 | 8.5% | 12.4% | -18.3% | -16.7% |
| Factor/style ETF | 0.75 | 0.93 | 8.9% | 11.1% | -19.7% | -13.3% |
| Sector ETF | 0.50 | 0.73 | 6.4% | 10.1% | -22.8% | -17.7% |
| Bond ETF | 0.72 | 0.91 | 2.1% | 2.1% | -3.3% | -3.2% |
| Commodity ETF | 0.77 | 0.94 | 10.9% | 14.5% | -32.7% | -28.8% |

Among the decorated widths, `c3_d20` is the modal per-symbol Sharpe winner and
carries the best medians:

| Variant | Full-universe median Sharpe | Median CAGR | Median max DD | Median Calmar | Per-symbol winner share |
| --- | ---: | ---: | ---: | ---: | ---: |
| `c3_d20` | 0.80 | 15.2% | -29.4% | 0.54 | 37.0% |
| `c3_d100` | 0.77 | 14.5% | -29.0% | 0.52 | 19.1% |
| `channel` | 0.76 | 15.1% | -32.4% | 0.48 | 32.9% |
| `c3_d55` | 0.78 | 14.6% | -29.2% | 0.54 | 8.5% |
| `c3_d10` (current V1) | 0.73 | 13.3% | -30.4% | 0.46 | 2.4% |
| `c4_d10` | 0.49 | 8.5% | -39.0% | 0.23 | 0.2% |

Notes:

- **Current V1 is `c3_d10`** (chandelier 3 ATR, `exit_len=10`) - the weakest
  chandelier in the sweep. V1's exit should widen the reversal channel 10 -> 20.
- On the fast 20/10 entry, `c3_d20` means `exit_len == entry_len`: exit when the
  price closes back through the 20-day channel OR the 3 ATR chandelier trail is
  hit, whichever first. Simple and explicit.
- `c3_d55` and `c3_d100` are within ~0.03 Sharpe of `c3_d20` on almost every
  sleeve - the decision is "wide backstop, ~20", not "exactly 20".
- Bonds: `c3_d20`/`c3_d55`/`c3_d100` are identical (Sharpe 0.91, DD -3.2%) - the
  3 ATR trail binds first, the backstop width is irrelevant, so no bond
  exception. `channel` is terrible for bonds (54-bar holds, no trailing stop).
- BTC: `channel` still posts the highest raw n=1 numbers (Sharpe 1.32, CAGR
  46%) by letting a parabola run, but `c3_d20` (1.00 / 27.5% / -26.2%) and the
  decorated bucket beat plain on drawdown-adjusted terms. BTC's special-casing,
  if any, belongs to the direction stage, not the exit.
- `c4_d10` and `channel` are dropped as candidates.
- Only 13% of symbols keep the same exit winner across all three periods (more
  variants than stage 1, so lower) - reinforces picking the robust modal
  default, not chasing basis points.

## Stage 3 direction-architecture decision (awaiting user sign-off)

Method: `backend/temp/direction_architecture_experiment.py`. Entry cluster and
the stage 2 `c3_d20` exit are frozen. Each symbol runs three ways - `both`,
`long`, `short` (the short leg standalone). Delta = both - long is the short
side's marginal contribution. The standalone `short` leg and the own-buy&hold-
drift quintiles are the explicit de-bias controls: they separate "the Donchian
short entry rule is weak" from "this universe is a bucket of winners". 673
symbols, 2019 engine runs, primary cohort 660.

Decision:

| Rule | Value |
| --- | --- |
| **Direction canonical default (whole universe)** | Long only (`allow_short = false`) |
| **Direction asset-class exception -> long/short** | Bond ETFs, Bitcoin |

Full-history median short-side contribution, primary cohort:

| Scope | n | dCAGR | dSharpe | dDD-reduction | short-only Sharpe | % short +ve standalone | Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full universe | 660 | +0.5% | -0.24 | -10.5% | +0.14 | 72% | long only |
| Individual equity | 556 | +0.4% | -0.24 | -11.7% | +0.13 | 71% | long only |
| Broad index ETF | 15 | +0.3% | -0.36 | -5.3% | +0.07 | 80% | long only |
| Factor/style ETF | 13 | -1.0% | -0.57 | -6.0% | -0.01 | 46% | long only |
| Sector ETF | 11 | -0.8% | -0.43 | -8.4% | +0.02 | 64% | long only |
| Thematic/industry ETF | 36 | +3.1% | -0.14 | -8.1% | +0.28 | 69% | borderline -> long only |
| Commodity ETF | 10 | +1.5% | -0.20 | -10.5% | +0.22 | 100% | borderline -> long only |
| **Bond ETF** | 17 | +0.8% | **-0.06** | -0.9% | **+0.33** | 82% | **long/short** |
| **Bitcoin** | 1 | **+6.5%** | **-0.06** | -4.0% | **+0.41** | 100% | **long/short** |
| Crypto (ETH) | 1 | +1.8% | -0.28 | -24.1% | +0.31 | 100% | long only (DD blow-out) |

### The de-bias control changes the interpretation, not the default

Long-only is still the default, but **not because the short entry rule is
broken**. The standalone `short` leg has a positive median Sharpe (+0.13-0.14)
and is profitable for 72% of the universe. What kills the *combined* long/short
is that adding a low-magnitude, choppy short stream to a strongly drifting long
book raises volatility and stacks drawdowns faster than it adds return.

Individual-equity quintiles by the symbol's own buy&hold drift:

| Drift quintile | median B&H CAGR | dCAGR | dSharpe | short-only Sharpe |
| --- | ---: | ---: | ---: | ---: |
| Q1 (-32%..6%, flat / declining) | 2.2% | **+4.1%** | **-0.05** | +0.32 |
| Q2 (6..11%) | 8.8% | +1.2% | -0.17 | +0.17 |
| Q3 (11..15%) | 12.9% | -0.2% | -0.24 | +0.10 |
| Q4 (15..21%) | 17.1% | -0.5% | -0.30 | +0.08 |
| Q5 (21..93%, strong uptrend) | 27.8% | -1.3% | -0.32 | +0.04 |

The short-side drag rises monotonically with drift. On the flat/declining names
(Q1) the short side is Sharpe-neutral (-0.05) and adds +4.1pp CAGR. The
full-universe -0.24 is dominated by Q3-Q5 simply because a survivorship-biased
active universe is mostly winners. **This is a universe-composition result. A
point-in-time or drift-balanced universe should re-run stage 3 - the default
could move toward long/short there.**

### The user's intuitions, tested

- **"Illiquid small caps are two-directional"** - not supported. Dollar-volume
  quintiles are flat: Q1 (lowest, ~$2-80M/day) dSharpe -0.26 vs Q5 -0.24, no
  trend in the standalone short. The universe also has no true microcaps (least
  liquid active name still ~$2M/day median, most >$100M), so it is largely
  untestable here, but within range there is no liquidity effect.
- **The real version of that intuition is volatility, not liquidity.** Realised-
  vol Q5 (43-168% annual) has dCAGR +2.9% and short-only Sharpe +0.25 vs Q1
  -0.6% / +0.04. High-vol names are more two-sided - but it is a continuous
  gradient, not a clean cluster, so it becomes documented nuance, not a rule.
- **"BTC is definitely two-directional"** - confirmed. dCAGR +6.5% at a flat
  -0.06 Sharpe; standalone short Sharpe +0.41; in 2020-2022 the short leg added
  +13.7pp CAGR (the 2022 crypto crash). BTC is a long/short exception.
- **"Most are still long only"** - confirmed. Every drift quintile above Q1, the
  whole equity complex, and the traded watchlist (dSharpe -0.40) are long only.

### The two long/short exceptions

- **Bond ETFs**: dSharpe -0.06, standalone short Sharpe +0.33 (highest group
  share improving combined Sharpe, 29%). Per period +0.01 / +0.08 / -0.11 - the
  short leg paid strongly through the 2022 rate-hike bond bear (short-only
  Sharpe +0.68 that window) and gave a little back in 2023+. Second half of
  "bonds may need V2 parameters" (entry 100/50 is the first half). Operational
  note: `MUB` in this group is `hard_to_borrow` and is not a practical
  long/short name.
- **Bitcoin**: as above. ETH is kept long only - its combined drawdown blows
  out -24% with shorts on - so "crypto = long/short" is specifically BTC.

Thematic/industry and Commodity ETFs are the borderline cases: a real
bear-market CAGR case (+3.1pp / +1.5pp, positive standalone short) but a
persistent -0.14 / -0.20 Sharpe cost across periods. Default them long only; the
operator can flip either to long/short if the bear-market capture is wanted.

The engine keeps its short capability; V1 sets `allow_short` per asset class.
Stage 1 is undisturbed - entry Fast-winner share only rises under long only.

## Stage 4: portfolio aggregation - experimental design

The signal rules are frozen: entry cluster (Bond ETFs 100/50, else 20/10),
exit `c3_d20`, direction long only except Bond ETFs + Bitcoin long/short. Stage
4 turns the per-symbol daily signal into ONE cross-asset benchmark equity curve
by adding a risk layer. It is a robustness demonstration over a pre-declared
rule ladder, not an optimization. Nothing here re-touches entry or exit.

### Signal-to-P&L contract (no re-simulation)

The engine already returns, per symbol, a daily costed strategy return
`strat_ret_i(t)` for a one-unit position that follows the frozen rule (state in
{-1, 0, +1}, entry/exit costs and intrabar stops already inside it). The
portfolio holds `w_i(t)` units of that position, so

```
portfolio_ret(t) = sum_i w_i(t-1) * strat_ret_i(t)  -  rebal_cost(t)
rebal_cost(t)    = cost_bps * sum_i |w_i(t) - w_i(t-1)|   on scheduled rebalance days only
E(t)             = E(t-1) * (1 + portfolio_ret(t))
```

`w_i(t)` uses only information through `t-1`. This preserves the engine's stop
and cost behaviour exactly and adds only the position-resizing cost.

### Rule ladder (each variant adds exactly one layer)

| Variant | Position sizing | Portfolio scalar | Caps | Cross-asset |
| --- | --- | --- | --- | --- |
| **P0** equal-notional | `w_i = sign / N_on`, gross = 100% split equally across on-signals | none | none | none |
| **P1** inverse-vol | `w_i proportional to sign / sigma_i`, gross normalised to 100% across the on-signals | none | none | none |
| **P2** + vol target | P1, then `x k(t) = vol_target / trailing_portfolio_vol` | `k` clipped `[0, k_max]` | none | none |
| **P3** + caps | P2, then clip `w_i <= w_max`, renormalise; cap gross `<= G_max` | yes | per-position + gross | none |
| **P4** + sleeve budget | risk allocated to sleeves {equity, bond, commodity, crypto, other} by a fixed budget; inverse-vol within sleeve; then P3 caps | yes | + per-sleeve cap | fixed sleeve risk budget |
| **P4c** + correlation haircut *(robustness only)* | P4 with `w_i` additionally divided by a trailing-correlation crowding factor | yes | yes | correlation-scaled |

- `sigma_i` = annualised stdev of instrument i's underlying daily returns over a
  trailing window (default 60 trading days).
- `trailing_portfolio_vol` = annualised stdev of the P1 book's daily return over
  the same trailing window, lagged one day.
- Sleeve = the asset-class label already used in stages 1-3.

### Pre-declared parameters (rationale, not fitted; a robustness grid is shown, never optimised)

| Parameter | Default | Rationale | Robustness grid |
| --- | --- | --- | --- |
| Vol lookback | 60 trading days | ~1 quarter; standard for trend books | {40, 60, 120} |
| Portfolio vol target | **12% annual** (user choice) | ~60/40 vol, apples-to-apples benchmark | {10, 12, 15} |
| `k_max` (scalar leverage cap) | **report both 1.0 and 2.0** (user choice); headline picked from results | unlevered floor vs standard moderate-leverage trend construction | - |
| `w_max` (max single position) | 10% of NAV | no single name dominates | {5, 10, 15} |
| `G_max` (max gross exposure) | = `k_max` (so 100% or 200%) | leverage ceiling | - |
| Sleeve risk budget | equity 50 / bond 20 / commodity 15 / crypto 5 / other 10; inactive sleeves' budget redistributed pro-rata | equity is the deepest liquid trend sleeve; crypto hard-capped (one noisy asset) | vs equal-sleeve for contrast |
| Rebalance frequency | weekly (first trading day of each ISO week) | daily resizing is pure cost | {daily, weekly, monthly} |
| Cross-asset headline / robustness | **P4 fixed sleeve budgets** headline; **P4c** correlation-crowding haircut as a robustness check only (user choice) | "simple, declared, not in-sample-fitted"; keep P4c only if it clearly improves the 2020/2022 drawdown | - |
| Rebalance cost | `cost_bps` = 5 (engine value) | consistency; doubled in stage 5 | - |
| Cash yield | 0% | conservative, matches earlier stages | - |

### Scientific controls

- **No look-ahead.** Every vol / correlation / scalar input is trailing and
  lagged one day; fills at next open, matching `fill_at = open_next`.
- **Survivorship control.** Run the whole ladder twice: (a) full universe, (b)
  ETF sleeves + watchlist only (drops the 556 survivorship-heavy single names).
  The P0 -> P4 ranking and the vol-target behaviour must hold on both.
- **Benchmarks.** SPY buy&hold; 60/40 SPY/AGG monthly; equal-weight buy&hold of
  the universe. A trend benchmark that does not beat 60/40 on Calmar is not
  earning its complexity.
- **Crash windows.** Report the portfolio drawdown through 2018 Q4, 2020
  Feb-Mar, and 2022 explicitly, per variant.
- **Metrics.** CAGR, realised annual vol (was the target hit?), Sharpe,
  Sortino, max drawdown, Calmar, Ulcer index, worst rolling 12 months, worst
  1-day and 1-week, % time under water, average gross exposure, turnover/yr.
- **Determinism.** Same inputs -> same equity curve; record rule + params +
  universe + date range.

### Decision rule

Pick the **simplest `Pk`** such that adding the next layer does not materially
improve Calmar, max drawdown, or vol stability (especially through the crash
windows). Report the marginal effect of every layer. Hypothesis to test, not
assume: P1 beats P0 clearly; P2 fixes vol stability and cross-period fairness;
P3 trades a little CAGR for tail protection; P4 mainly helps the 2020/2022
correlated-equity drawdown; P4c is likely not worth its complexity. Expected
canonical: P3 or P4.

Script: `backend/temp/portfolio_aggregation_experiment.py`. Same conventions:
SQLite read-only, disposable outputs under `docs/temp/`, `--from-cache` reloads
the per-symbol engine pickle, `--cost-mult 2` for stage 5.

## Stage 4 portfolio-aggregation result (signed off)

Window 2016-02 to 2026-08, 673 symbols, weekly rebalance, vol target 12%.

### The absolute numbers are not credible - read only the ladder ranking

Every variant from P3 on prints Sharpe 2.6-3.6, CAGR 20-38%, max drawdown
around -9 to -14%, Calmar ~2-4. Those are fantasy figures for a trend
benchmark (real diversified trend books run Sharpe ~0.5, max drawdown -20 to
-30%). Causes, in order: (1) the universe is today's index membership = known
winners, and long-only trend on known winners is rigged; (2) no point-in-time
universe is available to fix it; (3) averaging 150+ mostly-winning trend lines
manufactures an artificially smooth curve. The `restricted` universe (drop the
556 single names) prints lower but still-inflated numbers with an **identical
ladder ranking** - which is the usable result. Treat all Stage 4 headline
metrics as descriptive and survivorship-inflated, exactly as every prior stage.

### Rule ladder (full universe, k_max = 1 unlevered / k_max = 2 moderate)

| Variant | CAGR (k1 / k2) | Vol | max DD (k1 / k2) | Sharpe (k1 / k2) | Calmar (k1 / k2) | 2020 COVID DD | 2022 DD |
| --- | --- | ---: | --- | --- | --- | ---: | ---: |
| P0 equal-notional | 36.9% / 36.9% | 11.9% | -18.7% / -18.7% | 2.71 / 2.71 | 1.97 / 1.97 | -7.6% | -18.7% |
| P1 inverse-vol | 17.2% / 17.2% | 8.9% | -18.7% / -18.7% | 1.82 / 1.82 | 0.92 / 0.92 | -9.0% | -18.7% |
| P2 + vol-target scalar | 15.7% / 21.0% | 8.3 / 13.6% | -18.7% / **-35.0%** | 1.81 / 1.47 | 0.84 / 0.60 | -8.7 / **-15.3%** | -18.7 / **-35.0%** |
| **P3 + caps** | 23.9% / 35.7% | 7.0 / 9.5% | **-9.2% / -10.3%** | 3.08 / 3.27 | 2.60 / 3.48 | **-3.6%** | **-9.2%** |
| **P4 + sleeve budgets** | 26.1% / 38.4% | 7.1 / 9.4% | -9.2% / -10.4% | 3.30 / 3.50 | 2.83 / 3.68 | -3.1% | -9.2% |
| P4c + corr haircut | 25.7% / 38.7% | 6.9 / 9.3% | -9.3% / -10.7% | 3.34 / 3.56 | 2.76 / 3.63 | -3.1% | -9.3% |

Benchmarks on the same window: SPY buy&hold CAGR 12.5%, Sharpe 0.83, max DD
-33.8%, Calmar 0.37; 60/40 SPY/AGG CAGR 8.2%, Sharpe 0.85, max DD -21.9%,
Calmar 0.38. 2020 COVID: SPY -33.8%, 60/40 -21.9%, P4 -3.1%.

### What each layer does (this is the real output)

- **P0 -> P1**: inverse-vol roughly halves CAGR (36.9 -> 17.2). P0's extra
  return is concentration in the high-vol names, i.e. survivorship bias
  amplified. P1 is the honest sizing baseline. Drawdown unchanged.
- **P1 -> P2**: the vol-target scalar alone. Harmless at k_max = 1; **dangerous
  at k_max = 2** - vol 8.9 -> 13.6%, 2022 drawdown -18.7 -> -35% - because the
  scalar levers a concentrated book up right before a vol spike. **The scalar
  must never run without caps.**
- **P2 -> P3**: the position cap (`w_max` 10% NAV) + gross cap (`G_max` = k_max)
  are the entire tail-risk layer. max DD -18.7 -> -9.2%; 2022 -18.7 -> -9.2%;
  2020 COVID -8.7 -> -3.6%; worst rolling 12 months -14.7% -> -0.4%. Critical,
  non-negotiable.
- **P3 -> P4**: fixed sleeve risk budgets add ~2pp CAGR and ~0.2 Sharpe, no
  drawdown change. Small, free, and it is the declared cross-asset rule the
  mandate asks for. Keep.
- **P4 -> P4c**: correlation-crowding haircut changes nothing material anywhere
  (Sharpe +/-0.05, DD +/-0.3pp, crash windows identical). **Drop P4c.**

Robustness grid (P4, full universe): not knife-edge on vol lookback
{40, 60, 120}, vol target {10, 12, 15}, or `w_max` {5, 10, 15} - Calmar stays
~2.8 (k1) / ~3.7 (k2). Rebalance frequency does matter: daily is clearly worse
(Sharpe 3.3 -> 2.6, turnover cost), monthly has a higher Calmar (~4.2) at lower
CAGR. Weekly is the defensible middle; monthly is a valid conservative
alternative.

### Decision

| Rule | Value |
| --- | --- |
| **Canonical portfolio construction** | **P4**: inverse-vol position sizing, portfolio 12% vol-target scalar, per-position cap 10% NAV + gross cap = leverage cap, fixed sleeve risk budgets (equity 50 / bond 20 / commodity 15 / crypto 5 / other 10), weekly rebalance |
| **Leverage - frozen headline** | **k_max = 1 (unlevered, gross <= 100%)** - the conservative floor; the bias-inflated backtest under-represents the risk that k_max = 2 adds |
| **Leverage - documented alternative** | k_max = 2 (gross <= 200%) for a live deployment that accepts the extra risk |
| **Dropped** | P4c correlation haircut; running the vol-target scalar without caps |

P4 is really "P3 + a declared sleeve budget"; P3 is the layer that matters.

## Stage 5 cost-x2 sanity check

Every stage script re-run with `--cost-mult 2` (doubled `cost_bps` and
`slippage_atr`). Outputs carry a `_cost2` suffix so the signed-off 1x snapshots
are preserved. Purpose: confirm the four decisions survive, not to re-optimise.
Absolute figures decline; decisions are what is checked.

| Stage | 1x decision | at 2x cost | Survives? |
| --- | --- | --- | --- |
| **1 Entry** | Fast 20/10 default (58.5% winner share); Bond ETFs Slow 100/50 | Fast 56.5%; Bond ETF Slow 10/17 (identical); Broad index Fast 14/15 (identical) | **Yes** - slight drift toward slower horizons, cluster unchanged |
| **2 Exit** | `c3_d20`, no exception; decorated beats plain by ~0.18 Sharpe | `c3_d20` still modal winner (36% full universe, 41% watchlist, 47% bonds), still best median Sharpe (0.75); plain 0.56 vs decorated 0.74; `channel` gap widens slightly | **Yes** |
| **3 Direction** | long only default; long/short for {Bond ETF, Bitcoin} | `keep_long_short == [Bond ETF, Bitcoin]` (identical); full-universe dSharpe -0.24 -> -0.25; standalone short Sharpe still positive (+0.10 universe, +0.29 bonds, +0.39 BTC) | **Yes** |
| **4 Portfolio** | P4 (P3 caps critical); P4c dropped; weekly rebalance | Ladder ranking identical. P4 Calmar 2.83 -> 2.43 (k1), 3.68 -> 3.14 (k2); maxDD ~0.5pp deeper; 2022 crash P4 -10.4% -> -11.0%. P4c still == P4 (dropped). Daily rebalance craters (Calmar 2.31 -> 1.49) - confirms weekly; monthly still highest Calmar (4.17 -> 3.69). | **Yes** |

All four decisions survive. The 2x-cost effect is a uniform, modest decline
(Calmar down ~15-20%, CAGR down 2-4pp, drawdowns ~0.5pp deeper) that penalises
turnover exactly where expected - slower entry horizons, the high-turnover
`channel` exit, the choppy standalone short leg, and daily rebalancing - without
moving any cluster boundary. Benchmark frozen.

The engine books configured basis-point cost in the daily-return path but not
the ATR slippage estimate in trade rows. Borrow fees, borrow availability,
crypto funding, cash yield, financing on gross > 100%, and ETF-versus-futures
structure remain explicit un-modelled limitations at both cost levels.

## Freeze contract

When the remaining stages are complete:

1. Record the fixed strategy rules and asset-class exceptions.
2. Record the dataset cutoff, universe definition, and engine version.
3. Record both normal-cost and cost-x2 results.
4. Name the frozen model `Naive Donchian V1 Benchmark`.
5. Prohibit further parameter optimization inside V1.
6. Require future models to report incremental value relative to this benchmark.

## Artifact map

- `backend/temp/turtle_vs_buyhold.py`: baseline Donchian versus buy-and-hold study.
- `backend/temp/turtle_vs_buyhold.sql`: supporting read-only inspection queries.
- `backend/temp/multi_horizon_experiment.py`: fixed multi-horizon experiment.
- `docs/temp/turtle_vs_buyhold_report.html`: baseline interactive report.
- `docs/temp/turtle_vs_buyhold_results.csv`: baseline symbol-level results.
- `docs/temp/turtle_vs_buyhold_summary.json`: baseline summary.
- `docs/temp/multi_horizon_report.html`: multi-horizon interactive report.
- `docs/temp/multi_horizon_symbol_results.csv`: symbol and variant results.
- `docs/temp/multi_horizon_period_results.csv`: predefined-period results.
- `docs/temp/multi_horizon_speed_events.csv`: fast-to-slower confirmation events.
- `docs/temp/multi_horizon_summary.json`: multi-horizon metadata and summaries.
- `backend/temp/exit_architecture_experiment.py`: stage 2, isolated exit sweep
  (`--from-csv` re-rolls without the engine sweep; `--cost-mult 2` for stage 5).
- `docs/temp/exit_arch_report.html`: stage 2 interactive report.
- `docs/temp/exit_arch_symbol_results.csv`: one row per symbol/exit variant.
- `docs/temp/exit_arch_period_results.csv`: predefined-period results.
- `docs/temp/exit_arch_summary.json`: stage 2 metadata and summaries.
- `backend/temp/direction_architecture_experiment.py`: stage 3, isolated at the
  frozen `c3_d20` exit. Runs `both`/`long`/`short` per symbol; drift/vol/dollar-
  volume quintiles as de-bias controls. `--from-csv`, `--cost-mult 2`.
- `docs/temp/direction_arch_report.html`: stage 3 interactive report.
- `docs/temp/direction_arch_symbol_results.csv`: one row per symbol, all 3 policies.
- `docs/temp/direction_arch_period_results.csv`: predefined-period results.
- `docs/temp/direction_arch_summary.json`: stage 3 metadata and summaries.
- `backend/temp/portfolio_aggregation_experiment.py`: stage 4, the P0-P4c rule
  ladder x {k_max 1, 2} x {full, restricted}. `--from-cache` reloads the
  per-symbol engine pickle (`docs/temp/portfolio_signal_cache.pkl`).
- `docs/temp/portfolio_agg_report.html`: stage 4 interactive report.
- `docs/temp/portfolio_agg_summary.json`: stage 4 ladder / crash / robustness.
- `docs/temp/portfolio_agg_daily.csv`: daily P1/P3/P4 curves, both universes and k_max.
- `docs/temp/*_cost2.{json,csv,html}` and `portfolio_signal_cache_cost2.pkl`:
  Stage 5 outputs - every stage script re-run with `--cost-mult 2`. The `_cost2`
  suffix means the signed-off normal-cost snapshots are never overwritten.
- (deleted) `backend/temp/exit_direction_experiment.py`: the flawed combined run.

All research scripts must open SQLite read-only and must not write to production
application tables. All four stage scripts accept `--cost-mult` (Stage 5) and
`--from-csv` / `--from-cache` (skip the engine sweep).
