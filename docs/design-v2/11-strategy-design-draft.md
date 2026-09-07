# Multiple strategies on the same asset

**Status: PARKED — unfinished discussion draft. Multiple-strategy behaviour is not implemented.**

There is no active implementation task for this framework. This file holds the
working design and open decisions; revise it in place when discussion resumes.
The [current application design](06-trend-and-timing.md) remains separate.

## 1. One asset, several independent strategy views

An asset can run several strategies. Each answers its own question and owns its
own signals, simulated position, trades, stops and performance.

For example, these hypothetical views can coexist:

| Asset | Strategy | Current view | Meaning |
| --- | --- | --- | --- |
| SPY | Long trend breakout | Long | A longer upward trend remains active |
| SPY | Short mean reversion | Short | A different model expects a shorter pullback |
| SPY | Short breakout benchmark | Flat | Its downside breakout conditions are absent |

This resembles separate PM research books. **Do not cancel the opposing signals,
pick a winner silently, or turn an exit from long into a short entry.** Display
the disagreement and let the user inspect the reasoning and time horizon.

Within an individual two-sided strategy, the existing rule still applies: one
position at a time, long, short or flat. Across independent strategies, opposite
positions are allowed in their separate simulations.

## 2. Shared strategies, flexible assignments

Use a small library of named strategies and reusable parameter presets. An asset
can have several assignments; one preset can serve many assets.

- A **strategy family** defines the trading logic, such as trend breakout or
  mean reversion.
- A **preset** specifies that logic's parameters and supported directions.
- An **assignment** enables a preset for an asset or an eligible asset group.

Start with common presets. Introduce asset-class presets only where experiments
support them; individual assets do not need their own optimised parameter sets.
Overlapping group assignments must not run the same asset/preset twice.

An experimental candidate is not automatically a live board strategy. The board
runs the deliberately enabled set, including any enabled comparison benchmarks.

**Research scope:** long strategies are the active development target. The
existing Donchian short remains a functional, fixed comparison benchmark and
infrastructure placeholder for future short strategies. Both directions remain
supported. Future short-strategy comparisons should show separate return,
drawdown and trade-count bars against that benchmark on matching assumptions.

## 3. Trend: collect views and help prioritise attention

**Run enabled strategies** evaluates all enabled assignments for their eligible
assets, reusing the existing market-data and calculation paths where applicable.
It does not run every optimiser candidate or trigger macro AI. Show progress and
each strategy's completion status. Compare results using a common cutoff, while
showing each asset's actual latest completed bar; markets have different calendars.
An old or failed result is labelled accordingly, never treated as flat.

Use an asset summary with expandable strategy rows:

| Summary shows | Expansion explains |
| --- | --- |
| Asset and priority group | Each enabled strategy and preset |
| Current long / short / flat views | Position, entry date, stop and simulated contribution |
| Recent entry confirmations and pending actions | Exact signal date and execution status |
| Agreement and disagreement | Which strategies contribute to each side |
| Multisectional momentum context | Its value and observation date |

Keep **priority groups** and **strategy selection** as separate controls. Priority
tabs decide which assets deserve attention; strategy filters decide which models
are being examined. The same asset can appear in several saved views without
becoming several distinct opportunities in the asset count.

Priority 1 / 2 / 3 can be saved asset groups, with an All assets view alongside.
Their membership and final names remain open. Within each group, show strategies
together rather than requiring a separate page for every model.

Distinguish a fresh signal, a pending next-open action, and an existing holding.
A long position entered months ago is useful context but is not a new buy signal.

## 4. Agreement within a time window

Show two different measures:

1. **Current agreement:** how many eligible strategies currently hold the same
   direction, even if their entries occurred far apart.
2. **Recent agreement:** how many confirmed the same-direction entry within a
   chosen recent window, with that signal still pending or its position active.

For example, a five-completed-daily-bar window could group Monday's and
Thursday's long confirmations. Five is a discussion example, not an established
optimal setting. Count each strategy once; distinguish pending entries from filled
positions. Exited or cancelled entries remain in history but leave active agreement.

Initially compare daily strategies using the asset's own completed daily bars.
Display the actual dates. Weekly and intraday strategies need an explicit common
time-window definition before they can join the same recent-agreement measure.

Show long agreement and short agreement separately. Three long views and two
short views means disagreement exists, not an unexplained score of “+1”. Missing
or stale results are excluded and coverage is visible, such as “2 agree / 3 current;
1 unavailable”. Historical agreement must use only information available then.

Closely related presets are not independent evidence: ten slightly different
Donchian settings should not look like ten separate confirmations. Show preset
detail, but group agreement by strategy family. If a family's presets disagree,
label it mixed rather than casting a clean directional vote. A family count is
still descriptive, not a probability of success.

Proposed default: comparison benchmarks remain visible but are excluded from
agreement ranking unless explicitly included.

## 5. Momentum, macro and eventual weighting

Start with transparent context: direction agreement, signal age, Multisectional
momentum, volatility and, optionally, the existing naive macro composite. Each
keeps its own label and date. No automatic macro AI calls.

These may help sort or filter attention. They do not silently alter a strategy's
entry, exit or recorded performance. Direction matters: negative momentum may
support a short thesis rather than simply being a universally “bad” score.

If a combined score later changes trades or allocations, it becomes a separately
named strategy or portfolio rule requiring its own experiment. Specify its
inputs, weights and missing-data behaviour. Agreement alone does not establish
that the combined approach performs better.

## 6. Timing: explain one asset through several strategies

Select an asset, then a primary strategy for its chart, trades, stops and equity
curve. Allow optional overlays from other strategies, with clear names and
colours. Every entry, exit and stop belongs to an identifiable strategy.

Keep one primary trade ledger visible at a time; offer a comparison table for
other strategies on matching dates, costs and capital assumptions. Long / Short
controls continue to filter display and contribution; they do not rewrite stored
trades or recalculate exits. A standalone long-only simulation is a separate
run/configuration, not the result of hiding short trades.

## 7. Storage and portfolio boundary

The current app assigns one long preset per asset and always runs an independent
fixed short benchmark. One saved symbol snapshot contains both directions.
Supporting arbitrary strategy families requires results identified by **asset + strategy
preset/version + run**. Refreshing one strategy must not erase another's current
result or history. Store the exact parameters with the result; market data remains
shared. This is a necessary implementation change, not a frontend-only feature.

Independent strategy simulations each have their own capital assumptions. Their
returns cannot simply be added or presented as one account's return.

The current Sizing page already provides long-only, short-only and fixed 50/50
combined portfolios. Extending this to arbitrary strategies requires decisions on
shared capital, gross and net exposure,
concentration and whether opposing views receive allocations. The signal board
can remain neutral about conflicts; an actual combined portfolio needs explicit
allocation rules. Portfolio decisions must preserve the underlying strategy views.

## 8. Current application boundary

The production default is long entry20 / exit55, ATR20 and an initial3×ATR stop,
without Chandelier. Equal capital is the default sizing method; inverse volatility
and inverse volatility with entry caps remain alternatives. One shared long
preset serves the asset classes; no individual-symbol tuning is required.

Sizing supports long-only, the fixed short benchmark and combined accounts.
The short benchmark remains entry20 / exit20, initial2×ATR and Chandelier3×ATR.
Combined accounts start 50/50 without capital transfers. Each side's contribution
and the funded account result are visible separately. Display filters never
rewrite the underlying trades or exit calculations.

These facilities support future short-strategy comparisons without claiming
that the current short benchmark is profitable. Short optimisation is parked.
Full-universe reporting is retained, while priority assets guide practical
choices. Research code belongs in `backend/temp`; reports, tables and charts
belong in `docs/temp` for review and a final archive commit.

Multiple assignments, new strategy families, agreement ranking and automatic
portfolio execution are outside the current implementation. They require a
separate discussion when this draft resumes.

## Still open for discussion

- Which additional strategy families should be compared with the fixed benchmarks?
- What belongs in each priority tab, and what should the default ordering be?
- What recent-signal window is useful for daily desk review?
- Should agreement remain a visible filter or influence a separately tested allocation rule?

This parked draft does not authorise multiple-strategy implementation.
