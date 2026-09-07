# Position sizing

`/sizing` provides a fresh allocation estimate and a historical portfolio
simulation. It places no orders and never invokes macro AI. The default is
priority assets, long only, equal capital, normal costs, $100,000 initial capital
and history from 2020. Whole-database and full-available-history runs are available.

Long signals use each asset's assigned preset, defaulting to 20/55 with an initial
3×ATR stop and no Chandelier. Short signals use the fixed 20/20 benchmark, initial
2×ATR and Chandelier3×ATR. Both sides remain functional; short optimisation is parked.

## Controls and allocation rules

| Control | Behaviour |
| --- | --- |
| Universe | Priority watchlist, bonds and major companies; or all stored OHLC history |
| Direction | Long only, short benchmark only, or combined |
| Equal capital | Each eligible asset receives an equal budget, including flat names |
| Inverse volatility | Budget proportional to inverse trailing 60-return sample volatility |
| Capped volatility | Inverse volatility with gross entry limits: symbol10%, equities/other ETFs70%, bonds40%, crypto10% |
| Costs | Normal or doubled fees, slippage and borrow |
| History | Full available history or 2020 onward; each begins flat after warmup |

Volatility uses only completed prior bars for historical entries, annualised
252 for equities and 365 for crypto, with a 1% floor. At least 65 prior bars
are required. An asset whose latest prior price is over seven calendar days
old receives no new allocation. Flat names retain their budget as cash;
unused or capped allocations are not redistributed to active signals.

Combined accounts start with a fixed 50/50 long/short capital split and no
transfers. Gross symbol and asset-class limits aggregate both directions.
Opposite positions do not cancel each other for sizing or reporting.

## Allocation today

This tab uses the saved Trend board and latest closing prices to estimate total
holdings for a fresh allocation. Pending entries can receive a budget; pending
exits are omitted. All eligible saved symbols, including flat names, determine
weights. Quantities round down to instrument increments and minimum order sizes;
short quantities are negative. Cost-aware budgets reserve entry fees and slippage.

It shows each asset's signal, volatility, signed units, gross value and weight,
plus gross allocation, estimated entry costs and unallocated capital. Actual
next-open prices will differ. These are fresh target holdings, not changes to
an existing broker account or rebalanced historical simulation positions.

## Historical simulation

The backend reuses production signal fills and the reviewed fixed-unit portfolio
accounting. At entry it calculates units from available capital and the prior-bar
weight, including trading costs in the budget. Units remain fixed until the
native strategy exit; positions are not resized daily. Caps apply at entry and
can drift as prices change. Historical units are fractional to isolate allocation
behaviour from instrument rounding.

Cash earns zero interest. Short-sale proceeds are reserved rather than treated
as extra spending money. Short liabilities are marked with signed units; falling
prices produce gains and rising prices losses. Normal costs are 5 bps plus
0.05×ATR each side and 2% annual short borrow; doubled costs use 10 bps, 0.10×ATR
and 4%. Borrow availability and crypto funding are unverified assumptions of the
synthetic benchmark.

The daily account tracks equity, long holdings, short liabilities, reserved
capital, free capital and costs. Open trades are marked at the last known price.
Stale held prices remain marked and are counted; no exit is invented. Unfunded
native entries and funding-deficit days are reported.

The page shows portfolio CAGR, drawdown, ending equity, exposure, costs, calendar
returns and an equal-capital buy-and-hold reference. The reference uses the same
eligible history window, costs and initial capital. Asset contributions include
all symbols, even those with no funded trades, with a full CSV export and a
searchable trade ledger. Long and short price P&L less all costs reconciles to
the account's net profit. Portfolio CAGR is not median per-asset CAGR.

Allocation direction changes require a new simulation. Show-long/Show-short
checkboxes in the saved trade ledger only filter rows; they never alter the
saved allocation, exits or performance. Changed controls are visibly distinguished
from the last computed result.

## Background execution and storage

`POST /api/sizing/run` validates the request and submits `portfolio_simulation`
to the existing single worker. Progress, errors and cancellation use
`/api/data/runs/{id}`. Preparation reports each symbol, followed by portfolio
accounting and the buy-and-hold reference. Revisiting the page resumes monitoring
an active job. This action fetches no data and generates no macro AI output.

`GET /api/sizing/latest` returns the last successful result. The singleton
`portfolio_result` stores its exact settings, engine version, timestamp and
compressed curves, contributions, ledger and assumptions. A failed or cancelled
calculation leaves the previous successful result available. Changed prices or
assignments require an explicit new run; engine-version mismatch is labelled.

The full universe is the current stored database, not historical index membership.
Results use latest adjusted equity history and available Coinbase crypto history.
They describe this research universe and do not establish future performance.
