# Strategy research roadmap — current gaps and experiment design

**Status: DRAFT — research and product direction. No new experiments started;
no strategy, grade or leverage policy selected for production.**

The goal is a small research desk inside the app: several independent strategy
"PMs" evaluate the same assets, explain their long and short views, and help
decide whether an opportunity deserves no allocation, a small allocation, or a
larger one. Eventually, an explicit instrument and financing model can translate
an approved exposure into a feasible position. Donchian is one PM and the current
reference; finding its replacement is only one possible research question.

Keep the experience simple: run all enabled strategies in the backend, choose
one in the chart dropdown, inspect agreement and objections, then see an
explainable opportunity grade and proposed size. Complexity belongs in the
research and accounting needed to make those simple labels honest.

Part I maps the gaps and future work. Part II retains the first, bounded long
strategy experiment. Later phases require their own exact frozen rules before
execution; the examples in Part I are proposals, not validated trading settings.
The [agent work checklist](agent-work-checklist.md) breaks this roadmap into
small tasks and records ownership, dependencies and completion evidence. This
roadmap remains the rationale; use the checklist to resume execution without
re-reading completed work.

This is one working design, revised in place. Code and frozen research inputs
belong in `backend/temp`; reports, tables and charts belong in `docs/temp`.
Use the [current V2 paper](../strategy-experiments/naive-donchian-v2-result.md)
and current production code. Do not retrieve archived experiment contents.
Committing, force-adding ignored files, pushing and deleting research require
the user's explicit instruction; preparing or running research does not authorise them.
The [multiple-strategy draft](../design-v2/11-strategy-design-draft.md) supplies
earlier product ideas; implementation there remains parked. This roadmap resumes
the discussion without treating those future capabilities as already available.

## Part I — gaps and future work

### A. What exists, what is missing, and what would close the gap

| Gap | Current position | Work needed / evidence of completion |
| --- | --- | --- |
| Direction | Independent long Donchian and fixed short Donchian accounts exist. Keeping short functionality does not establish a useful short strategy. | Evaluate purpose-built short rules against the fixed short and cash, with separate costs, coverage and downside behaviour. A valid result is to keep short research available but allocate no short capital. |
| Strategy breadth | The app assigns a long Donchian preset and a fixed short benchmark; arbitrary PM families are not implemented. | Compare distinct entry/exit families, retain standalone ledgers, and identify complementary behaviour as well as possible replacements. |
| Multiple PMs | The same asset cannot yet have arbitrary independently saved family results. | Run every enabled assignment once, store each version independently, and inspect one through a chart dropdown without changing the computation set. |
| Agreement and denial | Multisectional momentum is advisory; there is no validated vote or veto portfolio. | Define positive confirmation, explicit opposition, abstention, missing data and exit separately; test each combination rule against its component strategies. |
| Opportunity size | Current sizing uses equal capital or volatility, not A/B/C opportunity grades. | Define an understandable base allocation and grade mapping; test whether grade changes improve a funded account after costs. |
| Instruments and leverage | Existing accounting models cash-funded long positions and a synthetic short benchmark. Instrument-specific financing and liquidation are not established. | Choose an instrument route, obtain its actual data and rules, and reconcile exposure, cash, margin, costs and forced exits. |
| Portfolio overlap | Existing portfolios support defined long/short books, not arbitrary PM capital sharing. | Track duplicate underlying exposure, correlated holdings and competing cash requests; reconcile every PM contribution to one funded account. |
| Evidence and data | V2 provides a reference; the documented SPY input issue, current-universe bias and previously inspected history limit inference. | Freeze reproducible inputs, resolve or label defects, retain every trial, and begin forward observation only after freezing the new rules. |

The user recalls a 2× position pressure test that did not exhaust capital with
stops enabled. Its exact settings and ledger have not been established in this
review. The current production `double` option doubles fees, ATR slippage and
short borrow charges; it is **not** a position-leverage control. Record these as
different tests. Obtain the earlier test specification from the user, or rerun a
new explicitly specified exposure test; do not silently retrieve archived work.
Historical survival also does not establish that the stop caused survival.

### B. Independent PMs, one shared data foundation

A PM is a named deterministic strategy and version, not an AI persona. Each has
an eligible universe, direction, time horizon, parameters, entry/exit rules,
stop rules, simulated positions, pending actions and standalone performance.
Research begins with a small number of distinct families, not many near-identical
presets masquerading as independent opinions.

1. Reuse a common frozen market-data snapshot. Run all deliberately enabled
   asset/strategy assignments, deduplicating overlapping group membership.
2. Save results by asset, strategy/preset version and run, including data cutoff,
   observation times, exact settings, success/failure and signal explanation.
   Updating one PM must not erase another. Do not mix different run cutoffs into
   an apparently current consensus; show incomplete coverage.
3. Keep each PM's position and ledger independent. A long exit means close that
   PM's long; it does not mean initiate a short or cancel every other PM's long.
4. Use the Timing dropdown to select the displayed PM's chart, stops, trades and
   equity. Dropdown changes are view changes. Trend provides an asset summary
   with expandable PM views and the existing four entry/exit directions.
5. Store the eventual combined portfolio as its own versioned policy, with its
   own funded ledger. Independent hypothetical PM accounts do not each get to
   spend the same shared dollar. No automatic macro AI calls are required.

Long and short views may coexist because their horizons differ. Display both
direction and horizon. First combination tests use compatible daily horizons;
weekly and intraday views need explicit alignment rules before joining a vote.

### C. Confirmation, veto and Multisectional context

| Term | Proposed meaning |
| --- | --- |
| Fresh entry | A PM confirms a new entry for the next available execution point. |
| Active support | A PM still holds that direction; this is context, not a fresh entry. |
| Opposition | An eligible PM explicitly supports the opposite direction on the defined comparison horizon. |
| Abstain / flat | The PM offers no directional support. This is not automatically a veto. |
| Unavailable | Missing, stale, failed or insufficient history. Never convert it to a negative vote or quietly shrink a required confirmation set. |
| Exit | An instruction belonging to a specific PM's existing position; separate from a vote on a new trade. |
| Hard veto | A predefined constraint blocks new allocation, such as stale required inputs, unavailable borrow, or an exposure limit. |

Count support by strategy family, with one family contribution. Conflicting
presets within a family produce a mixed label. Benchmarks remain visible but do
not vote by default. Show long support and short support separately, never hide
"three long, two short" behind an unexplained +1 score.

Freeze the supporting family set, required coverage and recent-signal window
before each test. A possible window is five completed asset bars; this is a
proposal. Historical votes use only signals still valid at the decision time.
Failed or stale required inputs block a new combined decision. Optional missing
context may reduce the grade only under a predefined rule.

Study these as separate policies, with the same capital and costs:

| Policy | Question |
| --- | --- |
| Standalone PM / fixed funded PM split | What do the components achieve without vote filtering? |
| Union | Does accepting a fresh entry from any selected family improve coverage after accounting for overlap? |
| Intersection | Does a fresh entry plus support from every named confirmation family improve outcomes despite fewer trades? |
| Explicit veto | Does blocking a fresh entry when a named opposing view is active improve outcomes? |
| Grade-based allocation | Does varying size add value beyond taking the same accepted trades at constant size? |

Multisectional ranking contributes a separate, dated context field. It must be
recomputed or replayed using data and universe eligibility available at the
historical decision time; today's saved ranking cannot label yesterday's trades.
For long proposals, relative strength might support the thesis; short rules may
use relative weakness. The thresholds and direction semantics require testing.
Momentum and price-action PMs may use overlapping information, so their agreement
does not imply independent evidence or a calibrated probability of success.

For the first shared-account proposal, an unresolved same-horizon long/short
conflict means no new allocation; the independent PMs continue to be shown.
Each accepted position retains a nominated originating PM whose exit/stop rules
govern it, subject to portfolio risk overrides. Confirmation loss blocks later
entries but does not silently rewrite an existing exit. A different rule that
closes on vote loss must be named and evaluated separately. A union policy must
freeze a deterministic owner when simultaneous PM entries target the same asset.

### D. Simple opportunity grades and the meaning of one lot

Use the user's intuitive convention as a research hypothesis: **C = 0.5 base
allocation, B = 1 base allocation, A = 2 base allocations**. Add **Skip = 0**.
These are allocation multipliers, not broker contract lots, leverage levels,
win probabilities or percentages of account equity at risk.

Proposed first grade definition, to freeze before testing:

| Grade | Explainable conditions | Size multiplier |
| --- | --- | ---: |
| Skip | No fresh eligible trigger, a hard veto, missing required evidence, or an unresolved directional conflict | 0 |
| C | Valid trigger from the originating family, all required inputs current, but no additional family confirmation | 0.5 |
| B | Valid trigger plus one distinct confirming family, no veto or conflict | 1 |
| A | B conditions plus supportive, current Multisectional context under a frozen direction-specific threshold | 2 |

Missing Multisectional context cannot create A. It may leave a proposal at B if
that input is explicitly optional. Save the reasons with the grade. More votes
do not automatically keep increasing size. The grade map is deliberately simple;
evaluate it without searching many score weights or relabelling losing grades.

Proposed base allocation: **5% of free deployable cash before the decision batch**.
Free cash excludes reserved orders, collateral, short-sale proceeds and any
configured cash buffer. Use one pre-batch cash snapshot for all simultaneous
signals; if requests exceed cash or limits, scale proportionally. Do not let
alphabetical order determine the largest position. Initially retain fixed units
until exit: a later grade change does not automatically pyramid or rebalance.

Example, ignoring costs for illustration: $20,000 free cash gives a $1,000 base
allocation. C requests $500, B $1,000 and A $2,000. These are cash budgets, not
estimated losses. A 5% cash allocation is **not** permission to lose 5% of equity.
For a linear position, show units × entry-to-stop distance plus costs as planned
stop loss, and report stressed gap loss separately; the stop estimate is not a
guaranteed maximum loss. Freeze per-position loss budgets and symbol, sector,
underlying and account exposure limits before any funded grade experiment.

This cash-based rule differs from production equal-capital sizing across eligible
names. Compare constant 1-base allocations with C/B/A allocations on exactly the
same accepted signals to isolate grading; also retain the production allocation
reference. Report trade counts, cash use, net contribution and losses by entry
grade. If A is not better supported in subsequent evidence, simplify the policy.

### E. Instrument choice and leverage are separate research decisions

Keep three quantities visible: grade multiplier, instrument exposure relative
to invested capital, and total account exposure. An A grade is not an automatic
instruction to borrow, buy a leveraged ETF, or increase the whole account to 2×.
A requested "1.5×" must specify whether it means a position multiplier or an
account gross-exposure target. For linear positions, account gross exposure is
the sum of absolute notionals divided by account equity; report net exposure too.
For leveraged products, also report estimated underlying exposure so buying a
2× product with borrowed cash does not hide compounded leverage.

| Instrument route | Additional model and inputs required before calling a simulation realistic |
| --- | --- |
| Cash equities / ETFs and spot crypto | Actual tradeable prices, fees, increments, calendars and liquidity assumptions; starting reference |
| Margin-funded equities or ETFs | Financing balance/rates, collateral eligibility, initial and maintenance margin, broker liquidation policy, adverse gaps and changing requirements |
| Borrowed short equity | Locate/borrow availability, changing borrow cost, recalls, dividends owed and short margin; synthetic short results are not execution feasibility |
| Leveraged / inverse ETFs | Actual product candles and inception, objective/reset frequency, distributions, splits, tracking and spreads; do not multiply the underlying's whole-history return |
| Futures / perpetuals | Contract multiplier, collateral, mark and liquidation prices, margin changes, expiry/roll or funding, and venue-specific execution |
| Options | Historical quotes/spreads, expiry/strike, volatility, exercise/assignment and nonlinear exposure; defer until appropriate inputs exist |

Choose one leveraged route for the first feasibility study; product and broker
selection remain open. Do not introduce all routes at once. Strategy signals may
come from an underlying while execution uses another instrument; record the
mapping, calendar, entry/exit timing and whether stops reference the underlying
or product. Match valid product history rather than inventing pre-inception fills.
With actual product returns, distinguish embedded expenses from separately charged
costs to avoid deducting the same expense twice.

A stop-market order does not guarantee the stop price, especially through gaps.
[FINRA's order-handling notice](https://www.finra.org/rules-guidance/notices/21-12).
Margin borrowing also introduces interest and possible broker liquidation.
[Investor.gov's margin-account bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-29).
Many leveraged/inverse ETFs target daily returns; multi-day returns depend on
the return path and reset mechanics.
[FINRA's non-traditional ETF FAQ](https://www.finra.org/rules-guidance/key-topics/etf/non-traditional-etf-faq).
These explain modelling gaps; actual terms must come from the selected product
and venue at implementation time.

First test unlevered allocation. Later compare explicitly defined 1×, 1.5× and
2× exposure scenarios, recording whether units are fixed or exposure is reset,
and when rebalancing occurs. Historical tests and synthetic shocks are separate
outputs. Include adverse opens beyond stops, simultaneous correlated losses,
cost/financing increases, borrow withdrawal, missing execution and margin changes.
Report drawdown, minimum equity/free collateral, margin breaches, forced exits,
financing and worst gap loss. Define failure before running. Daily OHLC cannot
establish the exact ordering of every intraday stop and liquidation; use finer
data or label conservative scenario bounds. "Did not blow up" is only one result
under stated assumptions, not the criterion for approving leverage.

### F. Sequence the work and make each phase useful

| Phase | Deliverable | Condition for proceeding |
| --- | --- | --- |
| R0 — inputs and conventions | Frozen data/coverage; resolve or label the SPY issue; explicit warmup, funding and stress-test definitions | Reconciled sample trades and consistent comparable inputs |
| R1 — strategy breadth | Part II's long comparison; separately specify one purpose-built short candidate, initially a failed-rally short within a downtrend | Full standalone results against D / buy-and-hold for long and fixed short / cash for short; short thresholds, holding horizon and costs frozen before execution |
| R2 — independent PM infrastructure | Common result contract, run-all-enabled workflow, saved PM ledgers and chart dropdown | Each PM reproduces its standalone result; failed runs and versions remain distinguishable |
| R3 — joint decisions at constant size | Descriptive agreement first; then a small frozen set of union/intersection/veto and funded-split comparisons | Shared-capital ledger reconciles; overlap and missing-data rules tested; compare to each standalone PM |
| R4 — C/B/A allocations | Constant-size versus graded-size accounts on the same accepted entries, without leverage | Exposure and cash competition explained; grades evaluated without hindsight |
| R5 — one leveraged instrument route | Product-specific accounting and matched-history/stress comparisons | Financing, forced exits and stress limits modelled and disclosed; size/leverage policy separately reviewed |
| R6 — forward paper observation | Frozen enabled PMs, decision policy, grades and instrument assumptions; dated proposals and realised paper outcomes | Sufficient new evidence under predefined review criteria before production promotion |

Short-strategy design belongs early in R1; it need not wait for ranking, voting
or leverage. Leverage feasibility research can run alongside earlier phases, but
an unmodelled leveraged route cannot enter their reported funded results. Begin
dated forward signal collection as soon as a candidate is frozen; R6 evaluates
the fully specified policy without retroactively treating earlier observations
as evidence for later revisions.

The next work package is R0 plus the fixed long experiment in Part II and a
short-candidate specification. R1 supplies useful results even if consensus,
grades or leverage subsequently add no value. Do not launch a joint optimiser
across strategies × votes × grades × instruments. Each extra layer must explain
its incremental contribution before the next is added.

### G. Decisions to freeze when the relevant phase starts

- R1: exact short entry, exit, stop and time horizon; preserve the fixed short
  benchmark and allow the conclusion that cash is preferable.
- R3: enabled voting families, freshness window, required inputs, ownership of
  shared positions and explicit conflict/exit behaviour.
- R4: exact Multisectional threshold, cash buffer and risk/exposure caps; keep
  the 5% base and 0.5/1/2 grade proposal distinct from the production baseline.
- R5: which instrument and venue to model first, what 1.5× refers to, exposure
  reset rules, financing assumptions and predefined failure limits.

Later opportunity output should explain: asset and direction; originating PM
and horizon; confirmation and opposition; context date; grade and reasons;
base cash, requested and permitted size; instrument; planned stop loss and gap
stress; position and account exposure; and why a request was reduced or skipped.
Keep implementation identifiers available for audit, out of the everyday flow.

## Part II — first long strategy comparison

Question: using our stored assets, does buying strength, holding a broad uptrend,
or buying a pullback provide the most useful long approach after costs? A useful
outcome may be retaining Donchian, adding a complementary PM, or declining to
allocate to a candidate. This experiment isolates strategy breadth before adding
votes, grades or leverage.

### 1. Questions and comparisons

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

### 2. Data before strategy ranking

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

### 3. First experiment: fixed rules

Daily bars are each asset's own trading bars. Indicators use only completed
bars; all close-confirmed actions execute at the next available open. Start
each asset after **250 prior valid daily bars** for every first-stage candidate,
including buy and hold. This also provides a common start for the MA neighbours.
An asset with shorter history stays in coverage but has no comparable result.
For each reporting window, the first decision bar is the first bar in that
window with 250 prior valid bars. Begin flat, evaluate at that bar's close, and
permit first execution at its next available open. Buy and hold purchases at
that same earliest execution open. Warmup bars create no carried positions or
pending orders. If no following open exists, retain the asset in coverage with
no executable comparison. Record decision and execution dates explicitly.

| ID | Entry while flat | Exit while holding | Initial stop |
| --- | --- | --- | --- |
| D: Donchian V2 | Close above highest high of previous 20 bars | Close below lowest low of previous 55 bars | Fixed 3×Wilder ATR20 |
| M: moving-average trend | Close above SMA200 | Close below SMA200 | None |
| P: uptrend pullback | Close above SMA200 **and** Wilder RSI2 below 20 | Close at/above SMA5, close at/below SMA200, or the tenth held bar's close, whichever comes first | Fixed 3×Wilder ATR20 |
| B: buy and hold | First common execution open defined above | Remain invested through the reporting cutoff | None |

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

### 4. Common accounting and capital

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
  no leverage, cash interest zero. Active candidates share the production
  allocation convention: current prior-bar equity divided by the currently
  eligible asset count, including flat names. Units stay fixed until exit.
  Use the common 250-bar eligibility rule above rather than production's shorter
  warmup; eligibility must use information available at that time.
- Buy-and-hold funding is an explicit exception inherited from production:
  reserve initial capital divided by the frozen member count per asset, including
  names not yet eligible. Invest each reserved budget at that asset's first
  common execution open; unused budgets remain cash, without rebalancing or
  future capital injections. Report this delayed-entry cash exposure and its
  difference from active-strategy funding. It is not an identical dynamic-weight
  allocation rule; separate timing from allocation effects in the interpretation.
- All simultaneous entry requests use the same prior-cash snapshot and scale
  proportionally if cash is insufficient. Preserve production's conservative
  convention that same-day exit proceeds cannot fund that day's entries. Log
  rejected or scaled requests and cost reservations for reconciliation.
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

### 5. Historical evaluation and sensitivity

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

### 6. Decisions, not a league table of flattering numbers

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

### 7. Additional candidates and dependencies

| Roadmap location | Candidate | Additional design needed before execution |
| --- | --- | --- |
| After the initial R1 comparison | Monthly time-series momentum | Exact calendar lookback, month-end decision, common coverage and cash rule |
| After the initial R1 comparison | Range mean reversion | Fixed range filter, entry band, target, stop and maximum holding period |
| Separate breadth experiment | Relative-momentum rotation | Point-in-time eligible ranking universe, ranking score, top count, rebalance and capital rules |
| R3 | Fixed 50/50 strategy combination | Separate initial capital, no transfers, duplicated asset exposure and common costs |
| R1 short track | Failed rally within a downtrend | Exact rebound/failure rules, exits and holding horizon, borrow/funding feasibility, fixed short and cash comparisons |

Do not add these because the first batch disappoints and then report only the
best survivor. They require their own frozen questions. Current membership and
surviving stored names limit historical generalisation, particularly for rotation.
No new data family or macro AI is required for the first experiment.

### 8. Review outputs

One report in `docs/temp`, containing four main tables: coverage and data issues;
strategy/portfolio comparison; annual and asset-class stability; costs, stop
controls and neighbours. Three charts: funded equity/drawdown, return versus
drawdown, and asset contributions. Include the complete per-symbol table and
trade ledgers as machine-readable files, plus reproducible parameters and inputs.
As later phases are undertaken, extend that report with the PM comparison,
vote-policy results, grade contributions and instrument stress results, each
clearly identified by phase and frozen policy version. Do not present planned
experiments as completed evidence.

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
