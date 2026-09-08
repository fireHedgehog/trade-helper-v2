# Strategy comparison — experiment design

**Status: DRAFT — for discussion. No experiments started; no production change selected.**

Question: using our stored assets, does buying strength, holding a broad uptrend,
or buying a pullback provide the most useful long trading approach after costs?
A useful outcome may be retaining Donchian. A different strategy may also be
useful alongside it without being a better replacement.

This is one working design, revised in place. Code and frozen research inputs
belong in `backend/temp`; reports, tables and charts belong in `docs/temp`.
Use the [current V2 paper](../strategy-experiments/naive-donchian-v2-result.md)
and current production code. Do not retrieve archived experiment contents.
Committing, force-adding ignored files, pushing and deleting research require
the user's explicit instruction; preparing or running research does not authorise them.

## 1. Questions and comparisons

| Question | Comparison | Evidence to examine |
| --- | --- | --- |
| Do breakout rules add value over a simple trend filter? | Donchian V2 vs moving-average trend | Net return, drawdown, turnover and consistency across years |
| Does buying weakness within an uptrend help? | Pullback vs Donchian and moving average | Net return, cash time, holding periods and losses during falling markets |
| Are differences mostly caused by stops? | Moving average with/without the same initial stop; pullback with/without it | Change in return, drawdown and stopped trades |
| Is timing worth its cost? | Each long strategy vs buy and hold | Return sacrificed or gained for drawdown reduction and time out of market |
| Could two strategies complement one another? | Later, a fixed 50/50 funded combination vs each standalone account | Portfolio drawdown and net return, including when both lose together |

These are hypotheses, not promises of profitability. A comparison of whole
strategies does not isolate the entry rule: exits and time invested differ too.
The stop controls isolate one specific difference; they do not explain everything.

## 2. Data before strategy ranking

Use **every stored equity, ETF and crypto asset**. Freeze the symbol list,
priority membership, asset classes, available dates and data cutoff before running.
Use the production priority definition: watchlist, bonds, major companies and
BTC/ETH. The previous study had 678 assets and 60 priority names; record the
actual counts rather than forcing those historical numbers.

Keep every symbol in the coverage table, including insufficient-history and
unresolved-data cases. Never omit a losing symbol or silently call missing data
Flat. Report full-universe results; practical selection uses the frozen priority
group. Do not search individual symbols for their best parameter settings.

Use adjusted equity OHLC and Coinbase crypto candles. Before ranking, check
duplicate dates, missing/nonpositive values, OHLC ordering, gaps and extreme
intraday ranges. Flags require inspection, not automatic price clipping.

**Known unresolved example:** SPY's stored adjusted low on 2026-02-02 is 68.64
against an open of 685.90 and close of 691.70. A direct Alpaca request also
returns that low. Another ordinary full fetch is therefore not an established
repair. Verify against an independent historical source. Never guess 686.40 or
replace the low with the close. Retain source evidence for any research correction.
If unresolved, show the affected symbol and portfolios as provisional; do not
declare a winner using them. Repairing an input requires recomputing all
candidates on the same corrected snapshot, including Donchian and buy and hold.

Save one reproducible input snapshot with source, cutoff, parameters, symbol
membership and a content hash in the research outputs. The live database may
continue changing without changing an already running experiment.

## 3. First experiment: fixed rules

Daily bars are each asset's own trading bars. Indicators use only completed
bars; all close-confirmed actions execute at the next available open. Start
each asset after **250 prior valid daily bars** for every first-stage candidate,
including buy and hold. This also provides a common start for the MA neighbours.
An asset with shorter history stays in coverage but has no comparable result.

| ID | Entry while flat | Exit while holding | Initial stop |
| --- | --- | --- | --- |
| D: Donchian V2 | Close above highest high of previous 20 bars | Close below lowest low of previous 55 bars | Fixed 3×Wilder ATR20 |
| M: moving-average trend | Close above SMA200 | Close below SMA200 | None |
| P: uptrend pullback | Close above SMA200 **and** Wilder RSI2 below 20 | Close at/above SMA5, close at/below SMA200, or the tenth held bar's close, whichever comes first | Fixed 3×Wilder ATR20 |
| B: buy and hold | First common eligible open | Remain invested through the reporting cutoff | None |

The pullback thresholds are deliberately simple starting assumptions, not
published or validated optimal parameters. RSI2 uses Wilder smoothing; no losses
means 100, no gains means 0, and no movement in either direction means 50.
Equality to SMA200 leaves M unchanged. The entry bar counts as held bar one for P.
A time-limit confirmation on bar ten fills at the following open.

No pyramiding, averaging down or same-account simultaneous positions. Each
strategy owns one long position per asset. Different strategies can overlap.
Resting stops use entry price minus 3×signal-bar ATR; they are active from entry,
stay fixed, and gap through at the adverse open. Scheduled exits execute before
intraday stops. A stop exit can be followed by a fresh close-confirmed entry for
the following session, never another intraday entry invented from daily bars.
An exit-day close does not create a duplicate entry for an already held position.

Two predefined stop controls: **M3** adds that same 3×ATR stop to M; **P0** removes
it from P. All other rules stay identical. These are secondary explanations,
not extra chances to silently replace the primary candidates.

## 4. Common accounting and capital

- Reuse the production fill and fixed-unit accounting conventions, with separate
  strategy signal logic. Independently reconcile a small set of entry, gap-stop,
  channel/time exit and still-open examples. Matching two functions alone does
  not prove the financial accounting is correct.
- Normal cost per side: 5 bps of fill notional plus 0.05×ATR per unit.
  Stress cost: 10 bps plus 0.10×ATR. Charge each actual fill once, including the
  buy-and-hold purchase. Use the ATR available before the fill.
- Mark open positions at the last available close; do not invent a final exit
  or final exit fee. CAGR includes calendar time in cash. Realised trade returns
  and equity returns including open P&L have separate labels.
- Primary funded accounts: $100,000, long only, equal capital, fractional units,
  no leverage, cash interest zero. Use the production allocation method identically
  across candidates: eligible flat names keep their budgets in cash, and units
  stay fixed until exit. Eligibility uses information available at that time.
- Run both priority and full-universe portfolios. Also report each asset's
  standalone return. Median asset CAGR is not portfolio CAGR. Apply the same
  stale-price rules to every candidate; flag held stale marks and prohibit new
  funding after more than seven calendar days without a price.
- Preserve the fixed short benchmark (20/20, initial 2×ATR, Chandelier 3×ATR)
  as a separate comparison account. Do not optimise it or fold its loss into
  a long strategy's result. Funded short reporting uses 2% annual borrow,
  stressed at 4%, with the existing synthetic-borrow limitations stated.

Equal capital makes the capital convention common; it does not equalise risk
or market exposure. Report those differences before attributing returns to skill.

## 5. Historical evaluation and sensitivity

Run full available history and a separate **2020-onward** account starting flat,
using earlier bars only for indicator warmup. Use matching dates for paired
comparisons on each asset. The 2020-onward priority portfolio is the primary
decision window; full-history and full-universe results test its breadth.

Show each complete calendar year's return and drawdown, plus the partial latest
year separately. Within a continuous run, do not reset positions at year-end.
Separate-window runs do reset; label them accordingly. Show 2020–2022 and
2023–2025 as fixed subperiods, without selecting attractive market episodes later.

There is **no optimiser in the first experiment**. Freeze the above candidates
before generating results. Nearby-parameter checks change one input at a time:
M uses SMA150 and SMA250; P uses RSI entry thresholds 10 and 30. Keep every
other rule unchanged. D remains the production reference. This makes ten long
configurations including buy and hold: four primary, two stop controls and four
neighbours. Run all at normal and doubled costs; show all trials.

Use paired uncertainty estimates for portfolio return differences: resample
the same calendar-date blocks for all candidates and assets together, retaining
cross-asset co-movement and cash days. Align funded returns to a daily calendar:
equity-only accounts carry unchanged weekend marks; crypto accounts retain their
weekend returns. Proposed diagnostic: 2,000 moving-block resamples, 28-calendar-day
blocks and an 84-day sensitivity, fixed seed 20260908. Annualise the mean daily
return difference using 365.25; do not mix this with compounded CAGR.
Display 95% intervals for annualised mean-return differences, not a probability
of making money or a guarantee about CAGR. These are conditional diagnostics;
they do not remove prior selection bias or establish statistical significance
across all attempted variants. If the interval spans zero, describe the return
advantage as uncertain.

This history was already examined during V2 research. Calling a later portion
"out of sample" does not make it untouched. Any later optimiser must select
using preceding data only and evaluate the next period, with all tried settings
retained. Even that is historical validation. A genuinely forward assessment
starts after the new rules and data snapshot are frozen; results must be kept
separate from subsequent rule revisions.

## 6. Decisions, not a league table of flattering numbers

Lead with **net funded CAGR and maximum drawdown together**, followed by
time invested, turnover, costs, worst year and longest recovery. Do not change
the main metric after discovering which one favours a candidate.

| Possible conclusion | Proposed desk criterion, fixed before execution |
| --- | --- |
| Replacement candidate | Higher priority-portfolio CAGR and no deeper maximum drawdown than D under both cost levels; positive return difference in more than half of complete comparison years, with at least four such years available |
| Different tradeoff | Higher return with deeper drawdown, or lower return with shallower drawdown; present both numbers for a user decision rather than calling it superior |
| Complement candidate | Distinct holding/loss periods suggest a separate fixed-allocation combination test; low correlation alone is insufficient |
| Inconclusive / retain D | Unresolved data, weak coverage, sensitivity to one setting, or advantage disappearing with costs or concentration checks |

These are proposed operating criteria, not universal scientific thresholds.
Passing them earns review, not automatic production promotion. Show concentration
by removing each candidate's five largest positive contributors in a labelled
diagnostic and rerun **both sides of that comparison** on the same reduced
universe. Do not redefine the primary universe from this result. Show asset-class
and priority-subgroup results, noting that overlapping equities and ETFs are not
independent confirmations. A claim driven by a few names must say so.

## 7. Later strategy families

| Phase | Candidate | Additional design needed before execution |
| --- | --- | --- |
| 2 | Monthly time-series momentum | Exact calendar lookback, month-end decision, common coverage and cash rule |
| 2 | Range mean reversion | Fixed range filter, entry band, target, stop and maximum holding period |
| 3 | Relative-momentum rotation | Point-in-time eligible ranking universe, ranking score, top count, rebalance and capital rules |
| 3 | Fixed 50/50 strategy combination | Separate initial capital, no transfers, duplicated asset exposure and common costs |
| Later | Bear-market rally short | Exact rebound/failure rules, borrow/funding feasibility and fixed short benchmark comparison |

Do not add these because the first batch disappoints and then report only the
best survivor. They require their own frozen questions. Current membership and
surviving stored names limit historical generalisation, particularly for rotation.
No new data family or macro AI is required for the first experiment.

## 8. Review outputs

One report in `docs/temp`, containing four main tables: coverage and data issues;
strategy/portfolio comparison; annual and asset-class stability; costs, stop
controls and neighbours. Three charts: funded equity/drawdown, return versus
drawdown, and asset contributions. Include the complete per-symbol table and
trade ledgers as machine-readable files, plus reproducible parameters and inputs.

Label no-trade, insufficient-history and unresolved-data cases explicitly.
Maintain this design and the report in place, without a separate fix log,
changelog or daily narrative. Once reviewed, a short permanent result paper can
replace the working material under the user's archive-and-delete workflow.

## Research grounding

Time-series and cross-sectional momentum ask different questions; the later
momentum phases should preserve that distinction. [Moskowitz, Ooi and Pedersen](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum).

Trying many configurations makes selecting a misleading historical winner easier;
fixed primary comparisons and disclosure of all trials address part of that risk.
[Bailey, Borwein, Lopez de Prado and Zhu](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Trading costs can materially change conclusions about frequent reversal trading;
our normal/doubled assumptions remain approximations, not measured execution costs.
[Frazzini, Israel and Moskowitz](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies).
These sources motivate the design; they do not validate the specific rules above.
