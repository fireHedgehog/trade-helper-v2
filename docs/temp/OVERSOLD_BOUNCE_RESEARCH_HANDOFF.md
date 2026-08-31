# Oversold bounce (short-term mean reversion) — research handoff (DONE — negative)

> Scratch, kept only in this snapshot commit. Frozen conclusion:
> `docs/strategy-experiments/oversold-bounce-v1-result.md`. R1 event study ran;
> **no tradeable edge** (forward-return curve never peaks; losers and gainers
> drift alike; hit rate a coin flip). Nothing built. R2–R5 not run — no point.

Mean reversion is the **opposite** of trend: there is no "let it run". The
edge decays in **days**. So the whole strategy hinges on a short, fixed,
pre-declared exit — the discipline is that you never hold past it hoping.

Same philosophy as the Turtle work: one full-universe default rule; an
asset-class exception only on large + stable evidence; the goal is a clean
controlled experiment, not an exception.

## What already exists (do NOT rebuild)

The Multisectional page already computes, per symbol:

- `return_5d`, `reversal_5d_percentile` = universe percentile of `−return_5d`
  (100 = biggest 5-day loser).
- `sector_relative_reversal_percentile` (sectors with ≥ 3 members).
- `is_reversal_watch = max(reversal_5d_percentile,
  sector_relative_reversal_percentile) ≥ 90` — gets its own table, no momentum
  weight.

That is the **entry screen**. The page stays untouched. This research decides
the entry threshold + gates, the **exit** (the core question), direction, and
sizing.

## Research tree

1. **R1 — Entry screen** (threshold + quality/liquidity gate)
2. **R2 — Exit** (the alpha half-life — the whole ballgame)
3. **R3 — Direction** (long-only headline; overbought-fade short as a symmetry check only)
4. **R4 — Sizing** (many small fast trades — a different sizing question)
5. **R5 — Cost x2** (turnover-heavy — this matters more here than anywhere)
6. **Freeze** as `oversold-bounce-v1`

### R1 — Entry screen

| Dimension | Candidates |
| --- | --- |
| Signal | raw `reversal_5d_percentile` · `sector_relative_reversal_percentile` · `max(...)` (current `is_reversal_watch`) |
| Threshold | ≥ 90 · ≥ 95 |
| Quality gate | none · raw close ≥ $5 + in the liquid top-100 · + must be above `SMA_200` (buy dips *in uptrends*, not falling knives) |
| Reversal window | 3-day · 5-day (the page uses 5) |

### R2 — Exit (the half-life)

**First, a diagnostic, not a sweep.** For the chosen entry bucket, compute the
average *cumulative forward return* at horizons 1, 2, … 20 trading days. It is
typically front-loaded (most of the bounce in the first 2–5 days) then fades to
zero or negative. `N` is anchored just past the peak of that curve.

Then the exit candidates (the "OR"s, tested cleanly):

| Key | Rule (whichever fires first) |
| --- | --- |
| `X0` time only | exit exactly `N` sessions after entry. `N ∈ {3, 5, 7, 10}`. |
| `X1` time · target | X0, or price back to `SMA_5` / `entry + 1·ATR`, whichever first. |
| `X2` time · target · stop | X1, plus `entry − 1.5·ATR` (falling knife → cut). |
| `X3` first green | exit on the first up-close after entry (very tight "take the bounce"), capped at `N`. |

**Invariant:** `N` is a fixed pre-declared number. No "hold a bit longer".
Select one canonical default + at most one asset-class exception.

### R3 — Direction

Headline **long only** (buy the oversold, expect it up). Symmetry check only:
`overbought_fade` = top-10% 5-day *gainers*, short for the mean-reversion down.
Report it, but the strategy is long-only unless the short side is unambiguously
Sharpe-additive and stable (it will not be — same universe bias).

### R4 — Sizing

Rebound is dozens of small, fast, overlapping trades. Test:

- equal-notional per open trade, cap `M` concurrent positions (`M ∈ {5, 10, 20}`)
- fixed-fractional: each trade risks `r%` of NAV to its ATR stop (`r ∈ {0.25, 0.5}`)
- inverse-vol per trade

Reuse the Turtle Stage 4 caps (per-position ≤ 10% NAV, gross ≤ `k_max = 1`).

### R5 — Cost x2

`--cost-mult 2`. This strategy churns; if the edge does not clear doubled
`cost_bps` + `slippage_atr`, it is not tradeable. Expect this to be the binding
constraint.

## Freeze contract

1. Record entry threshold + gate, exit rule + `N`, direction, sizing + caps.
2. Engine version, universe, dataset cutoff, both cost levels, the half-life
   diagnostic curve.
3. Name it `oversold-bounce-v1`.
4. No optimisation inside v1.
5. Conclusions → `docs/strategy-experiments/oversold-bounce-v1-result.md`.

## Engineering notes

- **Per-symbol engine shape.** Each oversold name is its own small trade with a
  time/target/stop exit — close to the existing Donchian engine's structure,
  not the portfolio-level path momentum needs. Could be a new `params.model`
  branch (`mean_revert`) reusing the ATR / fill / cost plumbing.
- **Walk-forward screen.** Same as momentum: recompute `return_5d` and its
  universe / sector percentile as of each session `d`, `d` walking daily.
  Reimplement compactly in `backend/temp/oversold_bounce_experiment.py`.
- Full-universe control + traded-subset report.
- SQLite read-only; disposable outputs under `docs/temp/`.

## Artifact map (this phase)

- `backend/temp/oversold_bounce_experiment.py`
- `docs/temp/oversold_bounce_*` — disposable outputs.
