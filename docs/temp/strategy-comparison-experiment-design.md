# Technical trading playbook: direction, location and timeframe evidence

Updated: 2026-09-15. Status: implementation specification for review.
This replaces the former experiment-design roadmap; the filename is retained for existing links.
Task ownership and progress live in [the agent checklist](agent-work-checklist.md).

## 1. Product purpose and working discipline

Help a discretionary trader find an actionable opportunity with an understandable entry,
invalidation, target and estimated cost, in either direction. Combine established techniques
instead of making one indicator responsible for every decision.

The core workflow is:

**Market structure -> price location -> entry trigger -> stop and target -> supporting evidence -> trader decision.**

- Uptrend: look for a long near support or the lower channel.
- Downtrend: look for a short near resistance or the upper channel.
- Established sideways range: consider buying the lower boundary and shorting the upper boundary.
- Transition or unclear structure: explain what is missing; do not invent a range.
- Weekly context, daily setup and 4-hour timing can reinforce or challenge the idea.
- Implement usable app features first; allow manual parameter tuning afterward.
- No comparative backtests, profitability admission gates, sweeps or new quantitative research.
  Functional checks of calculations, bar timing, persistence and UI remain necessary.
- The earlier request to bring SMA into production remains active. Deliver its long and short
  PMs without making SMA the entire strategy framework or reopening the experiment phase.

Sources below establish technical vocabulary and conventional methods. The composite rules,
numeric tolerances and workflow in this document are **our proposed editable app defaults**,
not source-endorsed optimal settings or a claim of profitability.

## 2. Established foundations

| Foundation | Source-backed meaning | App use |
| --- | --- | --- |
| Swing structure | Higher highs with higher lows describe an uptrend; lower highs with lower lows describe a downtrend. | Give every timeframe its own direction label and visible swing anchors. |
| Trading with swings | A trough in an uptrend can frame a long; a rally in a downtrend can frame a short. | Separate the trend from the entry location. |
| Support and resistance | Areas where price has previously encountered buying or selling; a broken level can change role. | Show levels, zones, breaks and retests with their dates. |
| Range trading | Price oscillates between identifiable support and resistance. | Two explicit setups: range long and range short. |
| Multiple timeframes | A larger timeframe supplies context while a smaller one helps identify entries. | Use weekly / daily / 4-hour roles without demanding identical direction everywhere. |

Sources: [Schwab: swing trading](https://www.schwab.com/learn/story/ins-and-outs-swing-trade),
[Fidelity: support, resistance and role reversal](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/support-and-resistance),
[IG: range trading](https://bts.ig.com/uk/learn-to-trade/ig-academy/range-trading/what-is-range-trading),
[IG: multiple timeframe analysis](https://www.ig.com/uk/trading-strategies/what-are-the-best-timeframes-in-forex-trading--210805).

The IG timeframe article is about forex. Its larger-context/smaller-entry principle is useful
here; its market sessions and timeframe ratios are not universal rules for equities or crypto.

## 3. Define high and low before generating a signal

### 3.1 Confirmed swing points

Start with a transparent five-bar swing detector: a central high exceeds the highs of the
two bars on each side; reverse the comparison for a low. This is the conventional fractal
shape described in [MetaTrader's Fractals documentation](https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals).
Confirmation arrives two bars later; [TradingView's Williams Fractal documentation](https://www.tradingview.com/support/solutions/43000591663-williams-fractal/)
also describes this lag. We use the shape as a structure primitive, without adopting the
entire Williams trading system.

Implementation decisions:

- Default left/right span: 2 completed bars, editable per timeframe.
- Persist pivot time AND confirmation time. A daily pivot at Monday cannot influence
  Monday's saved decision when its two confirming bars close on Wednesday.
- Use strict comparisons initially. Equal extrema produce no strict pivot; nearby confirmed
  points can still form an equal-high/low zone. Label flat-top/flat-bottom cases explicitly.
- If one wide bar qualifies as both a swing high and low, its intrabar order is unknown.
  Do not invent an alternating sequence from it.
- Maintain an alternating structural sequence. Before an opposite pivot confirms, a more
  extreme same-type pivot may supersede the current candidate only for subsequent decisions.
  Retain prior saved snapshots.
- Store candidate points separately from confirmed points. A chart can show a pending
  candidate, but a saved signal cannot describe it as confirmed.
- These are swing pivots, distinct from classic HLC-derived daily “pivot point” indicators.

### 3.2 Higher/lower/equal comparisons

Compare the latest two confirmed structural highs and the latest two confirmed structural
lows, within the same timeframe and structure version.

Proposed tolerance: epsilon = max(one instrument tick, 0.25 × ATR14).
For each assessment, use ATR from its latest completed bar and record the value.

| Label | Proposed comparison |
| --- | --- |
| HH | New high > prior high + epsilon |
| LH | New high < prior high - epsilon |
| EH | Highs differ by no more than epsilon |
| HL | New low > prior low + epsilon |
| LL | New low < prior low - epsilon |
| EL | Lows differ by no more than epsilon |

ATR describes movement size including gaps, not direction. Use Wilder smoothing, seed with
the mean of the first 14 true ranges, and retain a previous close for each true-range input.
[Fidelity: ATR definition and calculation](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr).
The 0.25 multiplier is our adjustable noise tolerance, not a textbook truth.

### 3.3 Market-state rules

| State | Proposed minimum evidence | Default behaviour |
| --- | --- | --- |
| UP | HH and HL in the current structural sequence; no completed close through the protected low minus epsilon | Seek long pullbacks; show upper obstacles. |
| DOWN | LH and LL; no completed close through the protected high plus epsilon | Seek short rallies; show lower obstacles. |
| RANGE | Two distinct confirmed reactions near each horizontal boundary, repeated traversal between them, and latest close still inside the boundaries plus tolerance | Seek long at support and short at resistance. |
| TRANSITION | A protected swing breaks, conflicting swing relationships, compression/expansion, or a range breaks | Suspend the old setup; display break/retest or wait conditions. |
| UNKNOWN | Insufficient or unusable bars/anchors | Explain unavailable evidence. |

The protected low is the most recent confirmed structural low supporting the UP sequence;
the protected high is the corresponding high supporting DOWN. Display the chosen point.
A break cancels that trend's continuation eligibility; it does not immediately confirm the
opposite trend. Require the opposite structure to form.

A single HH, one rising candle, price above SMA, or low ADX is insufficient to declare all
the other conditions true. Rising lows beneath flat highs may be compression rather than
a horizontal range. This state machine is our implementation convention.

### 3.4 Support/resistance zones and horizontal ranges

Proposed initial range construction:

1. Inspect up to 60 completed setup bars, using confirmed pivots available at the cutoff.
2. Pair two lows whose prices differ by at most epsilon; do the same for highs.
   Each pair's centre is its mean. Its zone extends epsilon on either side.
3. Require alternating boundary reactions, such as low-high-low-high or the reverse.
   Adjacent bars lingering at one boundary count as one reaction, not repeated tests.
4. Require upper-zone bottom > lower-zone top. A close outside a boundary by more than
   epsilon invalidates the old range; a wick alone is recorded as a test/sweep.
5. If multiple candidates qualify, select the one with the most recent final confirmation;
   break ties by the most recent first anchor, then stable anchor IDs. Show alternatives
   only on request. Do not select whichever later made more money.
6. Keep nearer internal obstacles visible. Recheck room to the first obstacle before a trade.
   A geometrically valid but narrow range can be untradeable after costs.

The 60-bar window, clustering and selection rules are editable engineering choices. A trader
can draw or adjust a zone; save author, time, reason, anchors and version rather than
silently changing the automatic result.

### 3.5 Sloping channels

A channel frames price movement between two boundaries; it is a separate drawing from a
rolling Donchian high/low envelope. [Schwab: trendlines and channel tools](https://www.schwab.com/learn/story/filtering-market-using-technical-analysis).

Proposed deterministic first version, using bar index on a linear price scale:

- UP: connect the latest two structural lows; project a parallel upper line through the
  highest positive high-pivot residual between those low anchors.
- DOWN: connect the latest two structural highs; project a parallel lower line through the
  lowest negative low-pivot residual between those high anchors.
- Require an opposite pivot between the anchors, correct slope sign, positive width, and
  no completed close beyond the protective boundary plus epsilon since the second anchor.
  Otherwise label the channel unavailable or broken.
- Store all three anchor IDs, their confirmation times, slope, offset and scale.
  Evaluate both boundaries at the current bar, not at an old anchor's price.
- Treat this minimum three-anchor channel as provisional geometry. Later reactions provide
  additional evidence; do not imply the opposite boundary is guaranteed resistance/support.
- Allow manual anchors and horizontal support/resistance alongside it. A trend setup may
  use a valid horizontal zone even when no reasonable parallel channel exists.

### 3.6 “Low” and “high” are relative locations

For a valid channel/range at time t, let lower = L(t), upper = U(t):

location = (price - lower) / (upper - lower)

Our first display defaults: lower quarter (0–0.25) = relatively low; upper quarter
(0.75–1) = relatively high; interior = middle. Values outside 0–1 stay visible as outside,
never clamped into an entry zone. Invalid width means location unavailable.

A long candidate needs proximity to identified support; a short needs proximity to identified
resistance. The outer-quarter label alone is not an entry trigger. “Low” does not mean down
a lot from an all-time high, and “high” does not mean merely expensive in absolute dollars.
After a bounce, classify the actual proposed entry too; a late entry may no longer offer room.

## 4. Four complete setup templates

These are proposed composite recipes built from the foundations above. Each gets its own
PM identity, direction, parameters and lifecycle. A short exit is a cover; it does not create
a long. A long exit does not create a short.

| Setup | Direction and location | Trigger after reaching the zone | Invalidation | First target |
| --- | --- | --- | --- | --- |
| Trend pullback long | Daily UP; pullback into support/lower channel | Completed bullish rejection or reclaim of a local swing high | Below the rejected support and relevant setup low, with buffer | Nearest resistance above entry, usually prior swing high |
| Trend rally short | Daily DOWN; rally into resistance/upper channel | Completed bearish rejection or loss of a local swing low | Above rejected resistance and relevant setup high, with buffer | Nearest support below entry, usually prior swing low |
| Range long | Valid daily RANGE; lower boundary | Rejection back inside, then upward confirmation | Below range support and rejection low, with buffer | First internal resistance; opposite boundary is a later target if clear |
| Range short | Valid daily RANGE; upper boundary | Rejection back inside, then downward confirmation | Above range resistance and rejection high, with buffer | First internal support; opposite boundary is a later target if clear |

Bounce/structural stop/target concepts: [Schwab swing-trade examples](https://www.schwab.com/learn/story/ins-and-outs-swing-trade).
Two-sided range concept: [IG range trading](https://bts.ig.com/uk/learn-to-trade/ig-academy/range-trading/what-is-range-trading).

Proposed trigger presets, selected explicitly rather than silently combined:

- **Rejection:** a completed candle overlaps the zone; long closes above its centre, above
  its open and in its upper half. Short mirrors all three comparisons. Zero-range bars fail.
- **Local structure reclaim:** after zone contact, a completed trigger-timeframe close moves
  above the latest confirmed local high for long, below the latest local low for short.
  Freeze the local trigger level at contact; later confirmation cannot backdate an entry.
- Default contact expires after 3 setup bars, or sooner if structure/zone breaks.
- The daily-only version evaluates daily triggers. The 4-hour version is a distinct preset
  and waits for actual intraday data. Do not invent intraday triggers from daily OHLC.
- Default stop buffer: epsilon from the setup timeframe. The stop follows the setup thesis;
  replacing a daily invalidation with an arbitrary tiny 4-hour stop is a different setup.
- Recompute estimated entry, target room and costs when the trigger arrives. Label the result
  waiting, actionable, invalidated or unavailable, with the reason.

Proposed lifecycle for the first app version: a close-confirmed daily entry becomes a pending
next-open action, consistent with the existing PM workflow. Before a modeled fill, recheck
invalidation and target room at the new price; cancel an obsolete plan rather than assuming
the previous close was available. Start with a fixed structural stop and the first target.
An opposite structure break can create an exit for that PM; trailing and partial exits are
separate editable presets. A new 4-hour trigger needs an explicit execution-clock extension,
not an intraday timestamp inserted into a daily-only contract. If one OHLC bar crosses both
stop and target, record the ordering ambiguity and use an explicit conservative convention
unless finer data resolves it. This is functional accounting, not a performance experiment.

Breakout/retest and failed-break reversal are subsequent templates, not exceptions that
silently turn the four recipes into a different strategy. Range breakdown cancels range-long
eligibility; range breakout cancels range-short eligibility. Re-entry requires a new valid
setup. An upper-band touch in an uptrend is not automatically a short.

## 5. Weekly context, daily setup, 4-hour evidence

Default roles are our product choice, not an optimal timeframe claim.

| Timeframe | Question | Display |
| --- | --- | --- |
| Weekly | What is the larger structure and where are major obstacles? | State, swing anchors, support/resistance, completed-through time |
| Daily | Is there a workable directional or range setup at a useful location? | Setup, zone, proposed entry, structural stop, first target |
| 4-hour | Is the local reaction supporting the entry now? | Rejection/reclaim, local structure, evidence age and availability |

Examples:

| Weekly | Daily | 4-hour | Interpretation |
| --- | --- | --- | --- |
| UP | UP, near support | Pullback ends with bullish reclaim | Supporting evidence for trend long |
| DOWN | DOWN, near resistance | Rally ends with bearish rejection | Supporting evidence for trend short |
| RANGE | RANGE, near lower boundary | Upward rejection | Range-long candidate; weekly upper boundary remains an obstacle |
| RANGE | RANGE, near upper boundary | Downward rejection | Range-short candidate |
| UP | UP, pulling back | Still DOWN | Pullback in progress; daily idea may exist while the 4-hour trigger waits |
| UP | DOWN, near resistance | Bearish trigger | Explicit countertrend short relative to weekly; show conflict and weekly support |
| Any | Any | Missing/stale | Unavailable evidence, never a neutral or confirming vote |

The top-down principle is described by [IG's timeframe guide](https://www.ig.com/uk/trading-strategies/what-are-the-best-timeframes-in-forex-trading--210805).
Our three-role combination and interpretation table are the proposed app design.

“Resonance” means explainable alignment of context, location and timing. It is not a probability,
nor three independent votes from related price series. A smaller downtrend can be the pullback
that creates a larger long opportunity. Several indicators saying the same thing should not
inflate confidence.

Proposed policy: higher-timeframe conflict is visible evidence. Countertrend templates are
labelled separately; a trader may accept them with a reason. Whether a particular preset
requires weekly alignment or a 4-hour trigger must be explicit in its saved version.
Missing required evidence blocks that preset; missing optional evidence leaves a partial card.

### Data and timing requirements

The current price/crypto tables are date-keyed, and the current PM contract is daily:
[migration 0003](../../schema/migrations/0003_data_management.sql) and
[PM contract](../../backend/app/features/pms/README.md).
A real intraday path is a product gap, not something an indicator setting fixes.

- Aggregate weekly OHLCV from compatible daily bars: first open, max high, min low,
  last close, summed volume; determine completion using the asset calendar.
- Obtain timestamped 4-hour bars, or aggregate smaller intraday bars. Daily bars cannot
  reconstruct their intraday price path.
- Specify provider/feed, instrument, adjustment basis, exchange timezone, session policy,
  bucket boundaries, bar open/close times, completion state and retrieval time.
- For a 6.5-hour session, a 4-hour bucket leaves a 2.5-hour session-end bucket. Label the
  shorter bucket; do not claim every equity day contains six equal 4-hour candles.
- For continuous markets choose explicit UTC buckets; for exchange sessions handle daylight
  saving and holidays through a calendar. Never align solely by the computer timezone.
- At decision time T, use only bars closed by T and pivots confirmed by T. A forming weekly
  candle may be shown separately, never substituted for the last completed weekly observation.
- Persist the exact source cutoffs and inputs. An intraday entry must use the daily setup
  already known then, not that day's future close.
- Daily-only production can ship first with “4-hour evidence unavailable.” Enabling a required
  4-hour trigger is a separate version and requires the data path.

## 6. Entry, cost, stop and target must form a usable plan

Proposed app calculations, for linear units on a consistent price basis:

- Long requires stop < expected entry < target.
- Short requires target < expected entry < stop.
- Gross planned risk per unit = absolute(entry - stop).
- Gross planned reward per unit = absolute(target - entry).
- Estimated loss at stop = gross risk + estimated round-trip costs to stop.
- Estimated reward at target = gross reward - estimated round-trip costs to target.
- Net reward/risk = estimated reward / estimated loss, only with valid positive denominators.
- Cost includes the relevant commissions, spread/slippage and holding-cost assumptions.
  Do not double count spread/slippage if already included in expected fill prices.
- If short borrow, financing or the executable instrument is unknown, show that uncertainty.
  Do not call an underlying-price short signal an executable spot-crypto short.

Illustrative arithmetic only: long entry 102, stop 99, target 110, total cost 0.20 per unit
on each outcome gives risk 3.20, reward 7.80 and ratio 2.44. Short entry 110, stop 113,
target 102 with the same assumptions gives the same arithmetic.

Default display preference: flag ratios below 2 for trader review, editable per preset.
Do not move the target past an intervening obstacle or move the stop inside the invalidation
merely to satisfy that preference. A discretionary acceptance can be saved with a reason;
it does not alter the original calculated plan.

Keep planned stop loss distinct from worst possible loss: a stop can fill beyond its trigger,
including after a gap. [Schwab: stop execution discussion](https://www.schwab.com/learn/story/ins-and-outs-swing-trade).

## 7. Evidence menu: combine complementary roles

The first four setup templates need only structure, zones, a trigger and risk geometry.
This menu provides later additions, not a reading or implementation gate.

| Technique | Proposed role in this app | Boundary |
| --- | --- | --- |
| HH/HL, LH/LL | Direction and protected swing | A lone new extreme is incomplete structure |
| Horizontal support/resistance | Location and obstacles | Show anchors and breaks |
| Sloping channel | Relative location during a trend | Channel geometry can be unavailable |
| Break and retest / role reversal | Continuation setup at a former boundary | Require observable break and reaction |
| Failed break and reclaim | Reversal evidence at a boundary | Do not assume every wick is a failure |
| Rejection candle | Trigger after zone contact | Candle shape alone is not a complete setup |
| SMA / EMA | Trend context and separate named PMs | Lag and price location remain visible |
| Donchian | Existing breakout family and channel levels | Preserve existing family semantics |
| ADX with +DI/-DI | Optional trend-strength and directional evidence | ADX alone has no direction |
| ATR | Zone/stop normalization and movement context | It does not predict direction |
| RSI | Momentum recovery/exhaustion evidence at a location | Oversold is not an automatic long |
| Stochastic | Optional range momentum evidence | Avoid duplicating RSI as another independent vote |
| MACD | Optional momentum/trend-change evidence | Related moving averages are correlated evidence |
| Bollinger Bands and bandwidth | Relative location and compression evidence | Band touch alone does not establish reversal |
| Keltner channel | Optional volatility envelope | Keep distinct from structural channels |
| Volume / OBV | Optional participation evidence | Missing or incompatible volume is unavailable |
| Anchored VWAP | Later event-anchored location evidence | Require an explicit anchor and adequate price/volume data |
| Volume profile | Later traded-price location evidence | Daily OHLCV does not identify actual volume at each price |
| Double top/bottom; head-and-shoulders | Later named structure templates | Define confirmation and invalidation when implementing |
| Flags, triangles, wedges | Later continuation/compression templates | Compression is not automatically RANGE |
| Weekly/daily/4-hour context | Agreement, conflict and entry timing | Related timeframes are not independent votes |
| Macro / multisectional context | Existing broader environment and relative strength | Context does not overwrite a PM's holdings |

Primary references for the indicator concepts:
[Fidelity SMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/sma),
[Fidelity EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema),
[Fidelity ADX and DI](https://www.fidelity.com/viewpoints/active-investor/average-directional-index-ADX),
[Fidelity RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI),
[Fidelity Bollinger Bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands),
[Fidelity indicator catalogue](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/overview),
[Schwab chart patterns](https://www.schwab.com/learn/story/how-to-read-stock-charts-and-trading-patterns).
Rows marked “later” are scoped ideas, not finished algorithm specifications. Read the relevant
primary definition only when implementing that feature.

Optional conventional ADX guideposts are below 20 for weak trend strength and above 25 for
stronger trend strength; the middle is ambiguous. These do not replace structural state.
RSI or a band touch can remain extreme during a trend. Display the interpretation and source
values rather than a generic “buy” badge.

## 8. PM independence, assessment and trader controls

Already implemented: independent saved PM results, run-all workflow, chart dropdowns and
descriptive family support. Reuse [the PM module](../../backend/app/features/pms/README.md)
and [assessment contract](../../backend/app/features/pms/assessment-contract.md).

A PM already holding while another enters, in either direction, is valid. Exits belong to the
originating PM. Selecting one chart does not decide which PMs run or participate in assessment.

Still to implement: the decision policy that combines these observations into an opportunity,
handles agreement/opposition/veto, incorporates macro/multisectional evidence and proposes size.
Existing descriptive support is not that allocation policy.

Proposed opportunity record:

| Group | Required content |
| --- | --- |
| Identity | Asset, setup ID, PM key/version, side, as-of time, engine/parameter version |
| Context | Per-timeframe state, completed-through time, availability and source/input references |
| Location | Swing/zone/channel anchors, automatic or manual origin, relative position |
| Plan | Contact time, trigger and expiry, expected entry, invalidation, stop, first and later targets |
| Costs | Instrument assumptions, estimated outcome costs, net reward/risk, missing inputs |
| Evidence | Supporting, opposing, unavailable and optional items with reasons and timestamps |
| Lifecycle | Watching, waiting, actionable, held, exit pending, invalidated or unavailable |
| Review | Trader accept/reject/override, reason, timestamp; original automatic assessment retained |

Map these fields into the existing contracts where possible; do not create a parallel PM engine.
Keep the signal, opportunity assessment and instrument/size proposal separate.

Future sizing can use familiar C/B/A labels and editable 0.5/1/2 base-lot multipliers.
These are discretionary policy choices, not calibrated probabilities. Define what one lot
means, available-cash basis, stop-risk cap and portfolio exposure limits before computing units.
Evidence agreement alone must not silently produce 1.5x leverage.

Neutral volatility is a distinct future instrument workflow. A defined-risk short iron condor
can be considered as a named candidate, but it requires actual options legs, strikes, expiry,
quotes, costs and payoff/invalidation rules. A RANGE or UNKNOWN label alone cannot recommend
selling volatility. [Fidelity: short iron condor structure](https://www.fidelity.com/learning-center/investment-products/options/options-strategy-guide/short-iron-condor-spread).
Instrument specifications belong in that later task; no options strategy is implemented here.

## 9. Delivery order and acceptance

Use [the checklist](agent-work-checklist.md) for current authorisation and task claims.

1. Deliver the already-requested SMA as ordinary production PMs, long and short, with saved
   results and overlays in the existing dropdowns. No renewed performance-comparison gate.
2. Deliver visible market structure, zones, location and manual review controls.
3. Deliver both trend-pullback directions and both range directions using daily data.
4. Add completed weekly context, then genuine 4-hour ingestion and optional timing evidence.
5. Add the opportunity composer, explicit assessment policy, grades and instrument sizing.

A production strategy task is done when it runs through the app, saves independently, can be
selected and understood on its chart, exposes entries/exits/stops/reasons for both directions,
and passes relevant functional checks. A document or a research result is not a shipped feature.

Functional examples to cover as each feature is implemented: HH without HL; LL without LH;
true range versus compression; protected-level break; pivot confirmation delay; equal extrema;
missing 4-hour data; forming weekly bar; mirrored long/short arithmetic; a nearer obstacle;
multiple PMs holding independently; manual changes preserving saved history.

No profitability testing or parameter search is required by this specification.
