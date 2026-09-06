# Position sizing

`/sizing` is a client-side allocation sandbox over the saved Trend board.
The operator supplies NAV, held exposure by sleeve and risk assumptions.
The page computes total target holdings, compares them with deployed exposure,
and explains the limiting constraints. It places no orders and saves no account
or holdings ledger.

## Inputs

- `GET /api/signals/board`: simulated positions, pending next-open actions,
  last close, `vol_60d`, sector, momentum and quantity rules.
- Macro: the last successful AI regime reading, falling back to the live
  deterministic composite. Only the zone affects sizing. The overlay is off
  by default; refreshing the page does not generate a new AI assessment.
- Controls: NAV, target volatility, maximum gross, name/sector caps, optional
  sleeve budgets, selected directions and held percentage of NAV per sleeve.

Pending entries and reversals use the intended direction and the last close
for provisional quantities. Pending exits are omitted from the target book.
Their next opening price remains unknown. New entries only filters the visible
rows by age; the target calculation and book totals still include all names
in the selected direction/watchlist scope.

## Total target calculation

Targets are independent of the deployed-by-sleeve inputs:

1. Inverse-volatility weights sum to `k_max × NAV`. Missing volatility uses a
   disclosed 25% assumption.
2. The per-name cap clips large weights and redistributes available excess
   proportionally among names below the cap. Unallocated amounts remain cash.
3. Each sleeve's total target is capped at `sector_cap × k_max × NAV`.
   Optional Equities/Bonds/Crypto/Other budgets cap those groups on the same
   reference gross. Deployed holdings are not subtracted from these caps.
4. Estimated portfolio volatility uses name volatilities and a fixed 0.35
   pairwise correlation, or the supplied override. All targets scale down by
   `min(1, target_volatility / estimated_volatility)`.
5. When enabled, macro scales targets by risk-on 1, neutral 0.65 or risk-off
   0.35, with adjustable neutral/risk-off multipliers. Risk-off also removes
   names with a known momentum rank below 50.
6. Quantities round down to whole equity shares or the crypto catalog's
   `min_trade_increment`, subject to `min_order_size`. Missing crypto metadata
   uses 0.00000001 units as a research assumption. Final target dollars equal
   rounded quantity times reference price. Unused dollars remain in cash.

The dollar/quantity output is the total desired holding. It is not the number
of additional units to buy or sell. Eligibility, live borrow availability and
actual fill prices require separate operator verification.

## Comparing with existing holdings

For each sleeve:

- Target: sum of final target weights.
- Room to target: `max(0, target − deployed)`.
- Exposure to reduce: `max(0, deployed − target)`.

The whole-book summary compares total target gross with total deployed gross.
That is a net difference: a portfolio can need both an addition in one sleeve
and a reduction in another. The sleeve view shows those differences explicitly.
Entering the proposed portfolio as existing holdings leaves its target weights
unchanged and shows no additional room or required reduction.

Cash at target is `max(0, 100% − target_gross)`. It describes the allocation at
the displayed reference prices after rebalancing, including quantity rounding;
it is not a broker cash balance. The volatility readout describes the estimate
before the volatility/macro scaling.

## Sleeves and verdicts

Sleeves are the 11 GICS sectors, Bonds, Crypto and Other. Equity sector metadata
drives GICS assignment; configured bond ETFs and crypto symbols have dedicated
sleeves. Untagged and commodity ETFs use Other. Related ETFs and individual
stocks can overlap economically despite occupying different sleeves.

Per-name verdicts are coarse sleeve-level review cues because actual per-name
holdings are not supplied:

- TRIM: deployed sleeve exposure exceeds its total target by more than 0.5% NAV.
- WAIT: macro excludes the name or its allocation cannot buy a minimum unit.
- BLOCKED: its sleeve is at target, or the whole book must be reduced before adding.
- LIGHT: there is room, but a cap reduces the name below its raw inverse-vol weight.
- ADD: there is room toward the sleeve target and no such cap reduction.

A TRIM cue does not establish that the operator owns the named instrument.
The actual holdings determine which positions to reduce.

## Page

Parameters and deployed-by-sleeve presets are on the left. Outputs include:
net room/reduction, gross exposure, cash at target, cap/volatility explanation,
sleeve target comparisons and k_max sensitivity. Grey represents held exposure
within target, green is room to add, red is exposure above target, and the tick
marks total sleeve target. The per-name table shows volatility, rounded target
weight, target dollars, target units and verdict; hover shows the calculation.

Targets are computed for all names in the selected scope before the recent-entry
and verdict display filters. The scenario resets when the page unmounts.
Refresh reloads cached signals and macro context; the operator fetches data,
recomputes rankings, runs Trend and reruns the AI assessment separately.
