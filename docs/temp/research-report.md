# PM research: strategy breadth and remaining gaps

**Current long-study decision: inconclusive; retain the existing Donchian default.**
SMA200 offers lower return with shallower drawdown in the predefined recent
priority comparison. The fixed pullback is highly sensitive to costs. Neither
earns automatic production promotion. Unresolved price flags prevent a validated
replacement claim, even where a control looks attractive.

The [roadmap](strategy-comparison-experiment-design.md) owns the frozen hypotheses;
the [agent checklist](agent-work-checklist.md) owns implementation state and live
job handoffs. This report records completed research, not a live trading policy.

## Inputs, conventions and accounting

Snapshot `20260914T032109Z`, database SHA-256 `6f4a0ade16bcb62eebba819078153f822c97ba3c2c3b5603cae7a826adafc711`. Equity history ends 2026-09-11 and crypto history 2026-09-13. All stored priced members are retained; catalog-only names have explicit missing-history coverage. No prices were corrected.

| Coverage / issue | Count or disposition |
| --- | --- |
| Priced assets / priority members | 678 / 60 |
| Comparable without flagged input | 576 |
| Provisional priced assets | 96 |
| Insufficient history | 6 |
| Catalog-only, no history | 32711 |
| Structurally invalid symbols | 0 |
| Extreme daily ranges / close returns | 217 / 37 |
| Approximate calendar gaps | 2 |
| SPY 2026-02-02 low | Raw 69.005; adjusted 68.64; unresolved, retained |

Complete [coverage](results/20260914T032109Z/coverage.csv), [issue evidence](results/20260914T032109Z/data-issues.csv), and [snapshot manifest](../../backend/temp/pm-research/inputs/20260914T032109Z/manifest.json) remain local. Peer session dates screen for gaps; they are not an authoritative exchange calendar. Adjusted equities, current stored membership, surviving symbols and overlapping ETFs limit generalisation.

All candidates start flat after 250 prior valid asset bars. The first reporting
close can confirm an action; the next asset open is the earliest fill. Asset-only
comparisons use the same decision, earliest-execution and final-mark dates across
all candidates. Funded accounts use a common calendar, including cash days.

Each funded account starts with $100,000, fractional fixed units, zero cash
interest and no instrument leverage. Active budgets equal prior equity divided
by currently eligible members, including flat names. Buy-and-hold instead reserves
initial capital across the frozen member count, including later/never eligible
names. This allocation difference and delayed cash deployment matter when comparing
timing rules. Entries share pre-batch cash and scale proportionally; same-day exit
proceeds cannot fund entries. New funding stops after seven days without a price;
held stale marks remain flagged.

Normal costs are 5 bps plus 0.05 ATR per unit per side; doubled costs are 10 bps
plus 0.10 ATR. Stops use signal-bar ATR; adverse gaps fill at the open. Scheduled
exits precede intraday stops. Final positions are marked without invented exit
costs. Doubled costs are **not** doubled positions. The user's recalled 2x-position
test remains unverified; no archive was retrieved and no instrument survival
claim is inferred.

Independent arithmetic fixtures reconcile entry costs, scheduled/gap exits,
same-day funding, open marks and short borrow/collateral. For example, $1,000 at
$100 with $0.05 fee and $0.10 slippage buys 1,000/100.15 units; an open $120 mark
has no closing fee. Every funded run asserts cash/equity identities and contribution
sums; completed results were also checked against ending equity. Frozen conventions
and per-run source copies/hashes support reproduction on the retained input.

## Primary long comparison

The decision window is 2020-onward, priority members, starting flat. Full-history
and universe accounts are robustness checks; no metric or candidate was selected
after seeing these outputs. CAGR and maximum drawdown are presented together.

| Strategy | Costs | CAGR | Max drawdown | Entries | Average cash | Worst complete year | Longest recovery days |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D: Donchian | normal | 12.07% | -17.77% | 733 | 19.80% | -15.64% | 765 |
| D: Donchian | double | 11.47% | -18.43% | 733 | 19.76% | -16.44% | 771 |
| M: SMA200 | normal | 11.09% | -15.22% | 1630 | 21.53% | -9.54% | 563 |
| M: SMA200 | double | 9.81% | -15.61% | 1630 | 21.35% | -10.84% | 716 |
| P: Pullback | normal | 0.79% | -4.86% | 5473 | 83.13% | -3.24% | 650 |
| P: Pullback | double | -2.91% | -19.14% | 5473 | 83.15% | -5.03% | 2398 |
| B: Buy and hold | normal | 19.06% | -26.55% | 60 | 0.88% | -22.88% | 680 |
| B: Buy and hold | double | 19.04% | -26.54% | 60 | 0.88% | -22.88% | 680 |

All 80 original funded scenarios are in [the full comparison](results/20260914T032109Z/long-diagnostics-v1/summary.csv). Whether a drawdown remains open at the cutoff is recorded separately from its longest historical duration. Entry turnover is gross entry notional divided by initial capital, not trade count; exact costs, exposure, stale marks and funding audits remain in the ledgers.

![Funded equity and drawdown](results/20260914T032109Z/long-diagnostics-v1/funded-equity-drawdown.png)

## Annual, asset-class and concentration stability

The year test uses complete calendar years only; 2026 stays explicitly partial. Asset-class numbers below are contributions to the shared account, not separately funded class returns. The asset median is a standalone statistic, not portfolio CAGR.

| Normal costs | Complete years | Years beating D | Median priority asset CAGR | Equity/ETF contribution | Bond contribution | Crypto contribution |
| --- | --- | --- | --- | --- | --- | --- |
| D: Donchian | 6 | - | 6.31% | 108.27% | 3.09% | 3.24% |
| M: SMA200 | 6 | 2/6 | 3.79% | 95.52% | 1.52% | 5.28% |
| P: Pullback | 6 | 1/6 | -0.64% | 7.16% | -2.28% | 0.51% |
| B: Buy and hold | 6 | 5/6 | 10.68% | 218.50% | 2.74% | 0.61% |

Machine-readable [annual returns and drawdowns](results/20260914T032109Z/long-diagnostics-v1/annual.csv), [fixed 2020-2022 / 2023-2025 subperiods](results/20260914T032109Z/long-diagnostics-v1/fixed-subperiods.csv), [asset classes](results/20260914T032109Z/long-diagnostics-v1/asset-class.csv) and [priority subgroups](results/20260914T032109Z/long-diagnostics-v1/priority-subgroups.csv) retain all scenarios. Positions are not reset at calendar-year boundaries.

Paired uncertainty uses the same date blocks for every candidate within each scope/window/cost comparison: 2,000 resamples, seed 20260908, 28-day blocks and an 84-day sensitivity. The statistic is annualized **mean daily return difference**, not compounded CAGR or a win probability. Crypto weekend returns and equity cash/weekend marks remain aligned. Primary candidate-minus-D 95% intervals are:

- M: SMA200, normal: 28-day blocks [-4.64%, 2.40%]; 84-day blocks [-3.96%, 2.39%].
- M: SMA200, double: 28-day blocks [-5.34%, 1.87%]; 84-day blocks [-4.71%, 1.90%].
- P: Pullback, normal: 28-day blocks [-17.57%, -4.73%]; 84-day blocks [-17.68%, -5.07%].
- P: Pullback, double: 28-day blocks [-20.82%, -7.79%]; 84-day blocks [-21.05%, -7.95%].

Full [paired diagnostics](results/20260914T032109Z/long-diagnostics-v1/paired-uncertainty.csv) include every predefined variant against D and buy-and-hold. Intervals spanning zero leave the return advantage uncertain. These conditional historical diagnostics do not remove data defects, repeated inspection or multiple-trial selection effects. No historical segment is called untouched out-of-sample data.

Concentration checks remove each candidate/cost case's five largest positive contributors, then **rerun both that candidate and D on the identical reduced universe**, recomputing eligible funding counts. The original primary universe is retained:

- M: SMA200, normal, remove NVDA,AVGO,TSLA,SOXX,LLY: candidate CAGR 7.08% / drawdown -12.89%; D 7.74% / -17.12%.
- M: SMA200, double, remove NVDA,AVGO,TSLA,LLY,SOXX: candidate CAGR 5.90% / drawdown -13.37%; D 7.17% / -17.78%.
- P: Pullback, normal, remove NVDA,AVGO,GOOG,SOXX,GOOGL: candidate CAGR -0.21% / drawdown -5.27%; D 9.04% / -15.41%.
- P: Pullback, double, remove GOOG,NVDA,SOXX,GOOGL,QQQ: candidate CAGR -3.66% / drawdown -23.03%; D 9.19% / -15.75%.

Exact [concentration results](results/20260914T032109Z/long-diagnostics-v1/concentration.csv) and reduced-account ledgers are retained.

M: SMA200 versus D has daily-return correlation 0.91; both lose on 33.6% of calendar return days in the normal-cost primary account. P: Pullback versus D has daily-return correlation 0.62; both lose on 24.0% of calendar return days in the normal-cost primary account. Distinct holding patterns can motivate a separately frozen funded-combination test; correlation alone does not justify allocation.

![Asset contributions](results/20260914T032109Z/long-diagnostics-v1/asset-contributions.png)

## Costs, stop controls and neighbours

All ten configurations were fixed before results. M3 adds the fixed 3 ATR stop; P0 removes it. Only SMA150/SMA250 and RSI10/RSI30 are neighbouring checks. Every trial is shown; none replaces the primary candidate because it happens to look better.

| Configuration | Normal CAGR | Normal drawdown | Doubled-cost CAGR | Doubled-cost drawdown |
| --- | --- | --- | --- | --- |
| donchian | 12.07% | -17.77% | 11.47% | -18.43% |
| buy-hold | 19.06% | -26.55% | 19.04% | -26.54% |
| sma200 | 11.09% | -15.22% | 9.81% | -15.61% |
| pullback | 0.79% | -4.86% | -2.91% | -19.14% |
| sma200-stop | 11.09% | -15.25% | 9.76% | -15.79% |
| pullback-no-stop | 1.00% | -6.52% | -2.53% | -17.05% |
| sma150 | 10.39% | -13.97% | 8.88% | -15.53% |
| sma250 | 11.27% | -19.53% | 10.19% | -21.05% |
| pullback-rsi10 | 0.70% | -3.93% | -1.39% | -9.80% |
| pullback-rsi30 | 0.18% | -6.13% | -4.83% | -29.13% |

![All configurations, return versus drawdown](results/20260914T032109Z/long-diagnostics-v1/return-drawdown.png)

The [complete standalone table](results/20260914T032109Z/long-diagnostics-v1/standalone-all.csv) has 27,120 asset/window/cost/configuration rows: 26,852 with trades, 28 valid no-trade accounts, and 240 unavailable histories. No-trade cash returns are not confused with insufficient history. Native funded ledgers, open marks and per-asset standalone curves are retained in each run's compressed files; [diagnostic provenance](results/20260914T032109Z/long-diagnostics-v1/run.json) identifies all input runs. The failed first SMA metadata-writing attempt remains recorded; its successful successor is `sma-comparison-v2`.

The frozen replacement criterion requires higher recent-priority CAGR and no
deeper drawdown than D at both cost levels, plus positive differences in more than
half of at least four complete years. The primary SMA and pullback do not meet
that combined criterion. Lower drawdown with lower return is a tradeoff, not
superiority. Retain D while input issues and further review remain unresolved.
No result here activates a PM, a vote, a grade or leverage.

## Independent short direction study

The separate [failed-rally specification](../../backend/temp/pm-research/short-specification.md) was frozen before execution. Both short PMs and cash use identical asset comparison dates, funding and costs. These are synthetic short accounts with 2% annual borrow at normal costs and 4% under doubled costs; borrow/product access is not established.

| Short comparison | Costs | CAGR | Drawdown | Entries | Borrow paid | Collateral-deficit days |
| --- | --- | --- | --- | --- | --- | --- |
| failed-rally | normal | -2.31% | -16.36% | 1792 | $920.20 | 0 |
| failed-rally | double | -3.92% | -25.17% | 1792 | $1,739.69 | 0 |
| fixed-short | normal | -5.81% | -40.17% | 1729 | $2,191.85 | 0 |
| fixed-short | double | -7.38% | -46.13% | 1729 | $4,148.73 | 0 |
| cash | normal | 0.00% | 0.00% | 0 | $0.00 | 0 |
| cash | double | 0.00% | 0.00% | 0 | $0.00 | 0 |

Complete [funded short results](results/20260914T032109Z/short-comparison-v1/funded-comparison.csv), [asset-only accounts](results/20260914T032109Z/short-comparison-v1/standalone.csv) and [run/source provenance](results/20260914T032109Z/short-comparison-v1/run.json) preserve all cases. Cash is a zero-interest, zero-trade reference. Inspect negative equity and free-capital/short-liability paths rather than treating a preset stop as a guaranteed loss limit.

Of 8,136 standalone coverage rows, 2 end with nonpositive equity and 5,348 have at least one synthetic collateral-reserve deficit day. These deficits are measured using the existing reserve convention, with no broker margin-call or forced-liquidation mechanism. They are not a count of observed broker failures.

- ECHO, fixed-short, full window, double costs: ending equity $-85.13 from $100,000; flagged inputs = True.
- ECHO, fixed-short, recent window, double costs: ending equity $-81.82 from $100,000; flagged inputs = True.

In the flagged ECHO series, the last short enters at 27.13 on 2025-08-04 and its trailing-stop exit fills at the adverse 54.11 open on 2025-08-26. Prior losses plus costs and that gap exhaust the synthetic account. This is a model failure case on unresolved inputs, **not a verified real-market event**; it cannot validate leverage safety or establish how a broker would have liquidated the position. The recorded ledger remains available for input investigation.

Borrow availability/recalls, dividend settlement, product mapping, margin changes and forced liquidation remain instrument gaps. No short allocation is justified solely by this synthetic comparison. Candidate selection and any production integration remain T25 review work.

## Application boundary and next work

Independent PM runs, persisted chart selection and descriptive family support are implemented. Funded vote policies, grade sizing, historical Multisectional context, actual instrument accounting and forward observation remain separate tasks in the checklist. Descriptive disagreement never overwrites a PM. No broker orders are placed by this research.
