# Naive Donchian V1 Research Handoff

Status: **IN PROGRESS - entry-horizon research is complete**

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

1. **Entry horizon - COMPLETE**
2. **Exit architecture - NEXT**
3. **Direction architecture - NEXT**
4. **Portfolio aggregation - LAST**
5. **Cost x2 sanity check - FINAL CONFIRMATION**
6. **Freeze Naive Donchian V1**

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

## Next: exit architecture

Keep the entry cluster fixed while comparing a very small set of economically
meaningful exits. A suitable maximum set is:

- Donchian exit channel only.
- 3 ATR Chandelier.
- 4 ATR Chandelier.
- One combined channel-and-ATR exit only if its rule is simple and explicit.

Do not sweep continuous ATR values or optimize exits per symbol. Compare CAGR,
Sharpe, maximum drawdown, Calmar, turnover, average holding period, and stability
across the predefined historical periods. Select one canonical default and allow
an asset-class exception only when the evidence is large and stable.

The current horizon experiment holds the 3 ATR Chandelier trail constant. Its
similar average holding periods across horizons mean it primarily identifies
entry strictness, exposure, and turnover. It does not finish the exit question.

## Next: direction architecture

Run this after selecting the exit architecture because short-side value can
interact with exit behavior.

Use this deliberately asymmetric policy:

- Long and short is the full-universe default.
- Long only is an exception cluster.

A group should become a long-only exception only when long only consistently
improves risk-adjusted performance, the short side does not add meaningful CAGR
or drawdown protection, and the result remains stable across periods. Do not
classify an asset as long only merely because it has positive long-run drift.

The existing speed-winner table does not answer this question. It compares entry
horizons inside one direction policy. The existing raw experiment includes both
long/short and long-only results, so the next analysis should build an explicit,
paired direction-contribution table at the already-fixed entry and exit rules.

## Last: portfolio aggregation

After the signal rules are frozen, add the minimum portfolio layer required for
a cross-asset benchmark:

- Volatility scaling at the position or sleeve level.
- A simple, declared cross-asset aggregation rule.
- Exposure and concentration limits that do not depend on in-sample winners.
- Explicit treatment of cross-market correlation.

Portfolio aggregation is a risk layer, not another opportunity to retune the
entry and exit rules.

## Final: cost x2 sanity check

Double all modeled transaction costs once, after every prior decision is fixed.
This is a robustness check, not a new optimization pass. The benchmark can be
frozen if its broad cross-asset behavior and primary cluster decisions survive,
even if individual CAGR values decline.

The engine currently books configured basis-point costs in daily returns but
does not book the ATR slippage estimate used in trade rows. Borrow fees, borrow
availability, crypto funding, cash yield, and futures-versus-ETF structural
differences remain explicit limitations.

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

All research scripts must open SQLite read-only and must not write to production
application tables.
