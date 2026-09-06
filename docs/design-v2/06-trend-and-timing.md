# Trend and Timing

Both pages use the two-sided Donchian engine in `features/signals`.
`ENGINE_VERSION="donchian-2"` identifies its execution and accounting rules.
A symbol has at most one simulated position at a time: long, short or flat.
Equities use adjusted OHLC; crypto uses raw OHLC. These are daily research
simulations, not broker positions or orders.

## Signals and fills

The entry channel uses the prior `entry_len` bars, excluding the current bar.
A close above its upper boundary signals long; a close below its lower boundary
signals short. The optional moving-average gate restricts entries by direction.

`fill_at=open_next` confirms the signal at the close and fills at the next
available session's open. Until that bar exists, `pending_action` contains the
action (`enter`, `exit`, or `reverse`), direction, signal date and fill timing.
Pending entries have no entry price and are not included as filled trades.
`fill_at=close` fills at the signal close; it earns none of the preceding
intraday move. This setting assumes execution at the observed closing price.

A close through the opposite `exit_len` channel schedules a model exit.
`stop_and_reverse` also opens the permitted opposite direction at that exit
fill. Scheduled orders execute at the next open before that session's range
is evaluated. An ordinary stop exit does not open a new trade on the same bar.

## Stops

The initial stop is entry price minus/plus `atr_stop_mult × ATR` from the
signal close. It is active immediately upon an opening entry.

The resting stop is tested against each session's low/high. A gap through it
fills at the adverse opening price; otherwise the fill is at the stop.
Only a surviving position receives a revised trailing stop after the close.
That revision applies from the next session:

- `chandelier`: best high/low observed since entry, minus/plus `chandelier_k × ATR`.
- `atr_trail`: close minus/plus `atr_trail_k × ATR`.
- `exit_channel`: the low/high of the latest completed `exit_len` bars.

Stops ratchet toward the price and never loosen. The displayed current stop
is the resting level for the next session. Hiding a direction preserves that
level for any position that remains visible.

ATR uses Wilder smoothing. Opening and intraday fills use the last completed
bar's ATR for slippage; close fills use that close's ATR. Daily bars cannot
establish the full path before an intraday stop: excursion statistics on a
stop day include the fill excursion, not an assumed later favorable move.

## Returns and metrics

Each trade uses fixed units sized to its entry notional. Costs per unit are
`fill_price × cost_bps / 10000 + slippage_atr × known_ATR` at each entry and exit.
They reduce P&L without moving displayed fill prices or stop levels.

For a closed trade:

`return = direction × (exit_price / entry_price − 1) − total_cost_per_unit / entry_price`

The daily curve marks those same fixed units to the close, or to the actual
modeled exit price on an exit day. Entry-day returns begin at the fill price.
Daily mark ratios compound to the trade's net return, including same-day exits,
opening gaps and both sides' costs. Closed trades compound sequentially; an
open trade is marked to the final close without inventing an exit fee.

Daily records carry `strat_ret`, `long_ret` and `short_ret`. A reversal date can
contain both sides' sequential contributions. Long/Short view filters use
those contributions and do not rerun the strategy or change saved history.

Trade statistics include win rate, expectancy, payoff, profit factor, R, SQN,
holding duration and excursions. Curve statistics include total return, CAGR,
annual volatility, Sharpe, Sortino, drawdown and Calmar. Annualization uses
252 observations. Buy-and-hold uses the same available price history.
All figures are single-symbol, rule-only research estimates.

## Parameters and saved state

`signal_strategies` supplies each symbol's parameters through
`assets.strategy_id` or `crypto_assets.strategy_id`, with a default fallback.
The standard entry channel is 20 sessions; the bond variant uses 100.
Both use a 20-session exit channel, 20-session ATR, initial 2×ATR stop,
Chandelier 3×ATR trail, next-open fills, 5 bps and 0.05 ATR per-side costs.
Research runs compute both directions; strategy direction flags do not limit
the board's scanning coverage.

`signal_events` stores filled trades. `signal_symbol_stats` stores the position,
next-session stop, price cutoff, volatility, metrics and `pending_action_json`.
Universe runs do not store chart payloads. A saved result with a different
engine version shows a recompute notice. Refreshing prices does not recompute
saved signals: the operator runs Trend afterward.

## Trend — `/trend`

Run trend backtest computes active equities, active crypto and the fixed
watchlist. The page shows pending next-open actions separately from holding
long, holding short and flat boards. Pending actions include the signal date;
holding boards are ordered by entry date.

The watchlist has table and chart views. Columns show state, entry, last price,
unrealized return, current stop, 60-day annualized volatility and the cached
Multisectional momentum score. Momentum is advisory context, not an entry rule.
Charts offer daily/weekly views, date windows and moving-average overlays.
Symbol links open Timing. The allocation note is a static research reference.

## Timing — `/timing/:symbol?`

The form resolves the symbol's assigned strategy. Run calls
`POST /api/signals/preview` with the edited parameters and persists nothing.
`GET /api/signals/timing/{symbol}` reads its saved result; `run_through_date`
is the saved price cutoff and `stale` indicates newer available prices.
`POST /api/signals/run` computes and saves a single-symbol result.

The page contains the price/indicator chart, entry and exit markers, pending
next-open action, position summary, trade history, metrics and equity curve.
Chart panes include volume, MACD, RSI and KDJ; D/W/M is a chart aggregation
choice, not a change to the daily simulation. Long/Short checkboxes filter
markers, history and performance contributions while preserving the actual
current stop for the visible position. A universe-only saved result requires
Run to generate chart overlays and daily performance contributions.
