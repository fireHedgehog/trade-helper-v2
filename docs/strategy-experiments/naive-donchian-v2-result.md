# Naive Donchian V2 — result

**Selected application default:** long breakout with 20-bar entry, 55-bar channel
exit and a fixed initial 3×ATR stop, without Chandelier. Use equal-capital sizing.
This is a practical return/drawdown choice, not a claim of optimal parameters or
superiority to buy and hold. Keep the short breakout as a fixed comparison book.

## Evidence and archive

Full experiment code, frozen inputs, trade ledgers, result tables, charts and
integration checks and production implementation are preserved in Git commit
[39084772934aec289c9681cdb2e4bf36013c55cd](https://github.com/fireHedgehog/trade-helper-v2/tree/39084772934aec289c9681cdb2e4bf36013c55cd).
The experiment folders are absent from the current checkout. This paper is the
permanent research reference; production behaviour is described in
[Trend and Timing](../design-v2/06-trend-and-timing.md) and
[Sizing](../design-v2/09-position-sizing.md).

**Agent instruction:** do not retrieve, restore or read archived experiment files
from Git history unless the user explicitly requests it. Use this paper and the
current production code for normal work. New experiments start in `backend/temp`
and `docs/temp`, with their own question and inputs.

## Research scope and steps

The experiments retain **all 678 instruments** with stored equity/ETF or crypto
OHLC. The fixed **60 priority assets** comprise the watchlist, bonds, major
companies and BTC/ETH; they guide the practical choice without restricting the
full-universe reports. Available history spans 2016-01-04 to 2026-09-05, with
Coinbase BTC/ETH data from 2021-01-01. Individual coverage differs.

1. **Baseline and accounting:** reconcile actual fills, signed fixed units, costs
   and daily marked equity. CAGR uses elapsed calendar years, including cash time.
   Open P&L is included; no hypothetical final exit cost is deducted. These
   execution/accounting assumptions govern V2; V1's reported figures are not a
   directly comparable baseline.
2. **Entry, exit and stops:** compare entry10/20/55/100/200 against exit10/20/55/100,
   then channel-only, initial ATR and Chandelier combinations. Separate direction
   runs distinguish long performance from the effect of adding shorts. A slower
   channel exit without Chandelier is the long shortlist, rather than one shared
   fast exit for every direction.
3. **Stability:** compare neighbouring long settings, normal/doubled costs and
   annual historical evaluation. Adaptive policies select using the preceding
   three years and carry positions forward with their entry rules. Bitstamp
   BTC/ETH provides a matched-date price-source sensitivity check. This history
   was already inspected; it is not an untouched holdout.
4. **Funded portfolios:** compare the two final 20/55 long variants, three sizing
   methods, fixed short and combined books, two universes and two history windows.
   Step 6 contains 128 portfolio scenarios. HONA, SKHY and SPCX remain reported
   but lack sufficient warmup for allocation.

## Selected rules

| Setting | Long default | Short comparison |
| --- | --- | --- |
| Entry / channel exit | 20 / 55 bars | 20 / 20 bars |
| Wilder ATR / initial stop | 20 bars / 3×ATR | 20 bars / 2×ATR |
| Chandelier | Off | 3×ATR |
| Execution | Next available open | Next available open |
| Role | Common preset across asset classes | Fixed infrastructure benchmark |

A closing breakout schedules entry; a closing channel exit schedules the next
open. Resting stops can exit intraday, with adverse gaps filled at the open.
Long and short production accounts run independently. Display toggles never
rewrite their fills or exits. There is no per-symbol optimisation requirement.

## What supports the choice

Step 5 priority-asset historical evaluation below reports **median individual
asset CAGR**, not a funded portfolio return. Medians of CAGR and drawdown are
separate summaries; they do not describe one representative account.

| Long rule / policy | Normal CAGR | Doubled-cost CAGR | Normal drawdown |
| --- | ---: | ---: | ---: |
| Baseline20/20, initial2×ATR + Chandelier3×ATR | 1.49% | 0.32% | −19.95% |
| 20/55, channel only | 6.47% | 5.84% | −31.71% |
| **20/55, initial3×ATR, no Chandelier** | **6.34%** | **4.89%** | **−30.87%** |
| Annual common-rule selection | 6.12% | 5.31% | −36.11% |

All nine neighbours around the selected rule had positive priority-median CAGR
under both cost levels. Asset-class selection could improve some historical
results, but did not establish a uniformly preferable rule set. A common preset
keeps the operating choice simple; the initial stop is a drawdown tradeoff, not
the winner in every window or cost comparison.

Step 6 below reports **funded portfolio CAGR / maximum drawdown**, normal costs,
2020-01-01 to 2026-09-05, starting flat with $100,000:

| Portfolio | Priority60 | Full universe678 |
| --- | ---: | ---: |
| 20/55 channel only, equal capital | 12.07% / −20.91% | 13.38% / −22.76% |
| **Selected long, equal capital** | **12.59% / −18.27%** | **13.30% / −20.74%** |
| Selected long, inverse volatility | 4.39% / −6.48% | 8.66% / -15.02% |
| Selected long, capped inverse volatility | 3.71% / −6.34% | 8.27% / -14.28% |
| Fixed short, equal capital | −6.05% / −40.85% | -7.88% / -51.88% |
| Selected long + fixed short, 50/50 | 5.54% / −11.73% | 5.62% / -14.42% |
| Equal-capital buy and hold | 19.38% / −26.96% | 17.23% / −33.48% |

The selected priority account ends at **$220,728**, with average gross exposure
**80.32%**. Doubled costs give **11.97% CAGR / −18.93% drawdown**. Across the full
available window, the selected equal-capital long returns 11.60% CAGR for priority
assets and 12.06% for the full universe. Channel-only returns 11.82% and 12.73%
respectively, with deeper drawdowns. The initial stop's benefit is protection in
this sample, not a universal return increase. Buy and hold earns more here.

## Allocation assumptions and limitations

Budgets include every eligible asset, even flat names. Unused budgets remain
cash; units stay fixed until exit. Volatility sizing uses prior-bar 60-return
sample volatility, annualised252/365 for equities/crypto with a 1% floor. Caps
apply to gross entry exposure: symbol10%, equities/other ETFs70%, bonds40%,
crypto10%; they can drift afterwards. Low-volatility bonds receive much more
weight under inverse volatility, explaining part of its lower return and risk.

Normal costs are 5 bps + 0.05×ATR each side; short borrow is 2% annually. Stress
doubles all three. Combined books start 50/50 without transfers, and short-sale
proceeds are reserved. Historical quantities are fractional; the current
allocation estimate rounds to instrument increments.

The universe uses today's stored names and latest adjusted prices, not historical
index membership. Selection across many inspected candidates introduces bias.
Crypto history is shorter; venue candles can change individual fills. Cash earns
zero interest; taxes, market impact, actual borrow availability, crypto funding
and broker margin liquidations are not modelled. Stale held prices remain marked
and flagged. None of these results guarantees future profitability.

Production promotion reconciles 4,068 fill comparisons and 72 portfolio cases
exactly against the retained experiment inputs. A separate current-database
check covers all678 instruments and nine recent full-universe portfolios, with
equity differences below one cent. These checks establish accounting agreement,
not predictive validity.

## Next work

Use the common long default and monitor subsequent, newly available data before
opening another parameter search. Retain both direction facilities and the fixed
short baseline for a future independently designed short strategy. Multiple
strategy families, assignments and signal agreement remain
[parked](../design-v2/11-strategy-design-draft.md). Any future broker workflow needs
its actual execution, financing and rounding assumptions evaluated separately.
