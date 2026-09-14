# PM research — inputs and results

**Status: in progress.** This is the evidence report for the
[agent checklist](agent-work-checklist.md). The [roadmap](strategy-comparison-experiment-design.md)
defines the hypotheses. No production strategy has been selected by this research.

## Conventions (T01)

Frozen machine-readable settings: [conventions.json](../../backend/temp/pm-research/conventions.json),
version `pm-research-1`, 2026-09-14. Warmup is 250 prior valid asset bars; first
entry is the next open after the first reporting close. No warmup position carries
into a reporting window. Buy and hold uses that same earliest execution open.

Active portfolios divide prior equity across currently eligible names, including
flat names. Buy and hold reserves initial capital across the frozen price-history
membership, including names that become eligible later or never do. This explicit
cash exposure difference is retained from production and must accompany comparison
results. Catalog-only symbols remain in coverage but are outside funded membership.

Simultaneous entries share one prior-cash snapshot and scale proportionally;
same-day exit proceeds cannot finance those entries. Costs reserve cash. Units
remain fixed until exit. Open positions are marked without hypothetical exit fees.

The current doubled-cost setting is 10 bps + 0.10 ATR per side and 4% annual
synthetic-short borrow, versus 5 bps + 0.05 ATR and 2% normally. It does not double
positions. The earlier 2× position test recalled by the user remains unidentified;
it is not represented as verified leverage evidence and no archive was retrieved.

## Snapshot and data quality (T02–T04)

Snapshot: `20260914T032109Z`, [manifest](../../backend/temp/pm-research/inputs/20260914T032109Z/manifest.json).
Database SHA-256: `6f4a0ade16bcb62eebba819078153f822c97ba3c2c3b5603cae7a826adafc711`.
Exported through a consistent read-only transaction; only market/catalog,
membership and strategy-definition tables were copied. Credential and AI tables
are excluded. The live database was not changed.

| Coverage | Count / dates |
| --- | --- |
| Stored price-history universe | 678 symbols, 60 priority |
| Equity / ETF bars | 1,720,661 across 676 symbols, 2016-01-04 to 2026-09-11 |
| Crypto bars | 4,164 across 2 symbols, 2021-01-01 to 2026-09-13 |
| Comparable without screening flags | 576 symbols |
| Comparable history with unresolved review flags | 96 symbols |
| Insufficient common history | 6 symbols |
| Catalog symbols without stored history | 32,711; reported but not funded members |
| Structural invalidity | No symbols detected by the implemented checks |

Full outputs: [coverage](results/20260914T032109Z/coverage.csv),
[issues](results/20260914T032109Z/data-issues.csv),
[summary](results/20260914T032109Z/data-summary.json).
Screening found 217 extreme ranges, 37 extreme close returns and two possible
calendar gaps. These are investigation flags, not proof that all those prices
are incorrect. Equity gap screening uses dates observed in peer histories rather
than a certified exchange calendar. Crypto source checks matched Coinbase.

**T04 disposition:** retain the snapshot unchanged. Every unresolved flagged
symbol and any funded portfolio including it remains provisional. The known SPY
row still has adjusted O/L/C 685.90 / 68.64 / 691.70 and raw O/L/C 689.58 /
69.005 / 695.41. Its problem is also present in raw prices; no independent repair
has been established here. Exploratory runs may continue, but no winner or
production promotion may be justified using these affected comparisons.

Meaningful snapshot tests passed: source changes do not change the frozen export;
credential tables are omitted; read-only writes fail; snapshot tampering is
detected; missing-history coverage and invalid OHLC / extreme-range / crypto-gap
flags are preserved. Two tests passed on 2026-09-14.

## Accounting examples (T05)

Five deterministic accounting tests passed on 2026-09-14 in
[test_accounting.py](../../backend/temp/pm-research/tests/test_accounting.py).
Expected values are calculated independently, rather than comparing two calls
to the same production calculation:

| Example | Independent expected result |
| --- | --- |
| Initial ATR and adverse gap | Prior TR 2, signal TR 5 => Wilder ATR20 2.15. Entry 105 gives stop 98.55; next adverse open 90 fills at 90, not 98.55. |
| Entry and exit costs | Entry cost 0.16/unit; next known ATR 2.1425 gives exit cost 0.152125/unit. Return is `(90 - 105 - .16 - .152125) / 105`. |
| Scheduled channel exit | A confirmed exit fills at next open 93, without substituting the intraday low 80. |
| Open mark | An open position remains open and carries entry costs only; no hypothetical final exit is recorded. |
| Funded purchase | $1,000 / (100 + .05 + .10) = 9.9850224663 units; cash after purchase is zero within floating-point tolerance. |
| Funded open/closed account | Open at final mark 120: `units × 120`. Closed at 95 with known ATR3: `units × (95 - .0475 - .15)`. Contributions reconcile to equity. |
| Same-day cash competition | X spends the $1,000 account, then exits for $1,200 on the day Y asks to enter. Y is unfunded because X's exit proceeds were unavailable to the prior-cash batch. |

## Reference portfolios (T06)

All 16 reference scenarios completed and reconciled on the frozen snapshot.
Results remain **provisional** because their universes include unresolved price flags.
These are the new common-warmup results, not a reproduction of the older V2 window.

[Complete summary](results/20260914T032109Z/references-v1/summary.csv) and
[run manifest](results/20260914T032109Z/references-v1/run.json). Compressed scenario
artifacts alongside them contain daily curves, funded trade ledgers and every asset contribution.

| Window | Universe | Costs | Book | CAGR | Max drawdown |
| --- | --- | --- | --- | ---: | ---: |
| full | priority | normal | long-initial | 10.51% | -17.83% |
| full | priority | normal | buy-hold | 17.78% | -29.29% |
| full | priority | double | long-initial | 10.02% | -18.49% |
| full | priority | double | buy-hold | 17.77% | -29.28% |
| full | universe | normal | long-initial | 10.54% | -20.46% |
| full | universe | normal | buy-hold | 14.90% | -34.94% |
| full | universe | double | long-initial | 9.79% | -21.26% |
| full | universe | double | buy-hold | 14.88% | -34.93% |
| recent | priority | normal | long-initial | 12.07% | -17.77% |
| recent | priority | normal | buy-hold | 19.06% | -26.55% |
| recent | priority | double | long-initial | 11.47% | -18.43% |
| recent | priority | double | buy-hold | 19.04% | -26.54% |
| recent | universe | normal | long-initial | 12.44% | -20.47% |
| recent | universe | normal | buy-hold | 16.37% | -33.17% |
| recent | universe | double | long-initial | 11.52% | -21.27% |
| recent | universe | double | buy-hold | 16.35% | -33.17% |

## Fixed pullback candidate (T18-T19)

All 8 funded scenarios and 2,712 standalone coverage rows completed in `results/20260914T032109Z/pullback-v1`. The 672 executable assets have matching decision/last-close windows; six short histories remain explicitly unavailable. Each funded ledger reconciles to ending equity within $0.00001. Frozen sources and hashes are retained with the run.

The 2020-onward priority account is the predefined primary window:

| Cost | CAGR | Maximum drawdown | Entries | Average cash fraction | Entry notional / initial capital | Worst closed trade P&L |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| double | -2.91% | -19.14% | 5,473 | 83.15% | 84.90 | $-495.83 |
| normal | 0.79% | -4.86% | 5,473 | 83.13% | 96.30 | $-484.09 |

At normal costs, the same-window Donchian reference returned 12.07% CAGR with -17.77% drawdown; buy-and-hold returned 19.06% with -26.55%. Pullback holds much more cash and turns over frequently: lower drawdown alone does not establish superiority. Doubling costs turns its primary-window CAGR negative. All comparisons remain provisional because of unresolved market-data flags. No candidate has been enabled in the application or selected based on these results. Predefined controls and complete diagnostics remain pending.

## Fixed SMA200 candidate (T16-T17)

All 8 new funded scenarios and 8,136 D/B/M standalone coverage rows completed in `results/20260914T032109Z/sma-comparison-v2`. Existing 16 funded references were reused. Every paired asset/window/cost has identical decision, earliest execution and final-mark dates, including the pullback comparison; 672 executable assets and six short histories are retained. The first attempt failed during metadata writing before saving any standalone result; its failed manifest and source remain in `sma-comparison-v1`.

| Cost | Recent priority CAGR | Maximum drawdown | Entries | Average cash fraction |
| --- | ---: | ---: | ---: | ---: |
| double | 9.81% | -15.61% | 1,630 | 21.35% |
| normal | 11.09% | -15.22% | 1,630 | 21.53% |

SMA200 has lower recent-priority CAGR and shallower drawdown than D under both cost levels. That is a tradeoff, not evidence of replacement. Unresolved price flags still make the experiment provisional. Annual, paired uncertainty, concentration and predefined-control diagnostics are required before the final T21 conclusion.
