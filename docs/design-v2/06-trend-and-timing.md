# Trend and Timing

Both pages use `features/signals`, engine version `donchian-4`. Each asset runs
its assigned long preset and a fixed, independent short benchmark. Each direction
owns its trades, position, stops and returns. Both may hold the same asset at once
in their separate research accounts. These are simulated positions, not orders.

## Current rules

| Setting | Default long | Fixed short benchmark |
| --- | --- | --- |
| Entry channel | 20 bars | 20 bars |
| Exit channel | 55 bars | 20 bars |
| Wilder ATR | 20 bars | 20 bars |
| Initial stop | 3×ATR | 2×ATR |
| Chandelier | Off | 3×ATR |
| Fill | Next session open | Next session open |
| Costs per side | 5 bps + 0.05×ATR | 5 bps + 0.05×ATR |
| MA regime / reversal | Off | Off |

The default long preset is `trend-long-v2`. One common preset serves all asset
classes, including bonds and crypto. The Strategies page can assign another long
preset. It cannot change the fixed short benchmark. Short optimisation and the
[multiple-strategy framework](11-strategy-design-draft.md) are parked.

Equities use adjusted OHLC and crypto uses raw OHLC. The paired engine starts
signals after at least 65 bars, or the longer required parameter warmup.

## Signal and stop execution

Entry channels exclude the current bar. A close above the prior entry-channel
high confirms a long entry; the short benchmark uses the prior low. A close
through the opposite exit channel confirms an exit. Confirmed orders fill at
the next available open. A last-bar confirmation remains a pending action,
with its signal date; it is not a filled trade.

The initial stop uses the signal bar's ATR and the opening entry price. It is
active on the entry day. A gap through a resting stop fills at the adverse open;
otherwise the fill is at the stop. Scheduled next-open exits execute before that
session's range is considered. A fresh closing signal after an exit can schedule
an entry for the following open.

The default long stop stays fixed until exit. With trailing enabled, a surviving
position updates its stop after the close, effective next session. Chandelier
uses the best high/low since entry and only tightens. The engine also supports
ATR and exit-channel trails for explicit long previews. Initial, channel and
trailing exits have separate enable flags. An optional close-fill preview earns
none of the preceding day's intraday move.

Opening/intraday slippage uses the last completed bar's ATR. Close fills use that
close's ATR. A stop-day excursion includes the fill excursion without assuming
the day's later favourable extreme occurred before the stop.

## Returns and direction views

Each trade holds fixed units. Costs per unit at entry and exit are
`fill_price × cost_bps / 10000 + slippage_atr × known_ATR`. They reduce P&L
without moving the displayed fill or stop. Closed trade return is:

`direction × (exit_price / entry_price − 1) − costs_per_unit / entry_price`

The daily curve marks those same units at each close or the actual exit price.
Entry-day P&L starts at the fill. An open trade is marked to the final close;
no hypothetical exit fee is charged. Daily compounding reconciles with trade
returns. Costs are charged once per actual side, including same-day round trips.

Long and short each have their own standalone curve. The combined Timing view
starts two accounts at 50% of initial capital each, without transfers: combined
equity is the average of their normalised equities. It is not the sum of their
percentage returns. Long/Short checkboxes select the stored direction metrics,
trades, pending actions, stops and overlays without changing any engine exits.
Daily state `2` means both independent accounts held positions.

CAGR uses actual calendar days / 365.25 and includes cash time. Trade statistics
cover realised trades; equity metrics also include marked open positions.
Volatility and Sharpe/Sortino use the 252-observation convention. Buy and hold
uses the same available symbol history. Timing is a single-symbol rule comparison
and excludes short borrow. Funded portfolio returns, borrow costs and separate
asset contributions belong on [Sizing](09-position-sizing.md).

## Saved state and refresh

Each symbol has one current snapshot, containing both directions. `signal_events`
holds both trade lists. `signal_symbol_stats.directions_json` holds each direction's
state and pending action; the same row stores exact long parameters, strategy id,
metrics and price cutoff, with engine version on its run. Primary state fields
remain available for compact single-row views, preferring a held long.

Universe runs save trades and states without full charts. A saved single-symbol
run includes per-direction equity, metrics and overlays in `signal_chart`.
An engine-version mismatch requires recomputation. Newer stored bars make Timing
stale; fetching prices does not itself recompute saved signals.

## Trend — `/trend`

The background run covers all stored equity history, active catalog assets,
active crypto and the fixed watchlist. Missing/insufficient history is not a
profitable or flat strategy result. Pending actions are separate from long,
short-benchmark and flat tables. An independently held asset may appear in both
direction tables. Watchlist summaries indicate when the short benchmark is
also held. Symbol links open Timing.

Watchlist table/chart views include price, entry, stop, momentum context and
60-return annualised sample volatility (252 equity / 365 crypto; 1% floor).
Multisectional momentum is context and never changes the breakout rule.
The board API also supplies all symbol rows, including flat assets, to preserve
the current sizing allocation denominator.

## Timing — `/timing/:symbol?`

The form resolves the assigned long preset. Run calls `/api/signals/preview`,
evaluates both independent directions and saves nothing. Parameter edits affect
the long preview only. `/api/signals/timing/{symbol}` reads the saved snapshot;
`/api/signals/run` computes and saves a symbol explicitly.

The default display is long; the browser remembers the operator's direction
selection. Charts include price, volume, MACD, RSI and KDJ. Daily/weekly/monthly
chart aggregation does not change the daily simulation. Full overlays and
per-direction curves require a preview after a universe-only saved run.

Research code belongs in `backend/temp`; reports, tables and charts belong in
`docs/temp` until reviewed and archived. Full-universe results remain available,
with watchlist, bonds and major companies guiding the practical selection.
