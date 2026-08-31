# Oversold bounce V1 — result: no tradeable edge

Frozen conclusion of the short-term mean-reversion research. The answer is
**negative** — there is no backtestable oversold-bounce alpha in this universe —
so nothing was built. This file exists so the question is not re-opened from
scratch.

## Archived — do not reproduce

The experiment code and raw outputs (`backend/temp/oversold_bounce_experiment.py`,
`docs/temp/oversold_bounce_r1_*`) were committed once at **`__SNAPSHOT__`** then
removed from the working tree in the next commit. Every number here is a
literal. **Do not fetch git history to "verify" or "reproduce".**

## What was tested

An **event study** (not a portfolio): 2016-01-04 → 2026-08-28, 676 active
equities/ETFs, SPY calendar. On each session `d` the universe is ranked by
`−return_Nd` (biggest losers first); names above a percentile threshold that
pass a quality gate are "entered" at the `d+1` close and their forward
cumulative return is recorded at horizons 1 … 20 sessions. This one computation
answers both the entry-bucket question (R1) and the alpha-half-life question
(R2).

Grid: **signal** {raw `−return_Nd` percentile · sector-relative percentile ·
`max` of the two} × **threshold** {≥ 90 · ≥ 95} × **quality gate** {none ·
top-100 by 20-day $-volume + raw close ≥ $5 · + above `SMA_200`} × **reversal
window** {3-day · 5-day}. 36 buckets; 1.56 M raw events.

## The result — hardcoded

### R1 / R2 — the forward-return curve has no peak

Mean forward cumulative return by horizon, for representative buckets (%):

| Bucket | +1 | +2 | +3 | +5 | +7 | +10 | +15 | +20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| raw ≥ 90, no gate, 5-day | 0.13 | 0.25 | 0.36 | 0.54 | 0.68 | 0.90 | 1.37 | 1.84 |
| raw ≥ 90, liquid, 5-day (headline) | 0.14 | 0.25 | 0.38 | 0.50 | 0.61 | 0.91 | 1.32 | 1.75 |
| raw ≥ 90, above SMA_200, 5-day | 0.16 | 0.28 | 0.39 | 0.53 | 0.62 | 1.04 | 1.44 | 1.92 |
| raw ≥ 95, no gate, 5-day | 0.13 | 0.28 | 0.40 | 0.59 | 0.73 | 0.95 | 1.43 | 1.97 |
| sector-rel ≥ 95, above SMA_200, 3-day (best of 36) | 0.24 | — | 0.62 | 0.81 | — | 1.44 | — | 2.81 |

Every one of the 36 buckets **peaks at horizon 20** (the longest tested) with
the mean rising monotonically. A real oversold bounce peaks at horizon ≈ 2–5
then decays — **this is the shape of plain upward drift**, not mean reversion.

### The symmetry check kills it

The same study on the **biggest 5-day gainers** (`return_5d` percentile ≥ 90 —
the overbought basket a mean-reverter would *short*):

| | +1 | +3 | +5 | +10 | +15 | +20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| oversold basket (raw ≥ 90, 5-day) | 0.13 | 0.36 | 0.54 | 0.90 | 1.37 | 1.84 |
| overbought basket (5-day gainers) | 0.05 | 0.19 | 0.37 | 0.89 | 1.33 | 1.74 |

The biggest losers and the biggest gainers have **the same forward return** —
both just inherit the universe's drift. Being this week's worst name carries no
information about next week.

### Hit rate is a coin flip, and it fails when it matters

Headline bucket (raw ≥ 90, liquid, 5-day), fraction of events with a positive
5-day forward return:

| Period | N events | hit rate @ 5 days | mean @ 5 days |
| --- | ---: | ---: | ---: |
| 2016–2019 | 7 400 | 55.9 % | 0.48 % |
| **2020–2022** | 8 241 | **49.7 %** | **0.21 %** |
| 2023–present | 10 206 | 54.0 % | 0.75 % |

≈ 52–55 % overall (barely above 50 %), **below 50 % in 2020–2022** — the period
with the most oversold events. And this is *before* costs, slippage, or a
concurrent-position cap, on a turnover of 25 k–190 k events.

## Conclusion

**Do not build `oversold-bounce-v1`.** The `reversal_5d_percentile` /
`sector_relative_reversal_percentile` / `is_reversal_watch` columns on the
Multisectional page stay as a **UI attention flag only** — a list of names that
just dropped hard, useful to look at, with no claim of a tradeable short-term
edge attached.

Why it fails here: the universe is trending survivor-winners. Dips in these
names *are* bought back — but on a multi-week timescale, which is already
captured by the trend engine (`naive-donchian-v1-result.md`) and the momentum
research (`xsec-momentum-v1-result.md`). There is no separate fast
mean-reversion premium to harvest.

If this is ever revisited, it needs a genuinely different universe (liquid
high-beta names *without* the survivor filter, or intraday data) — not a
re-tune of these thresholds.
