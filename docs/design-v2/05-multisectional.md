# Multisectional page

`/multisectional` — across the whole active universe, which symbols look
strongest by **price/volume alone**. A ranking, not an entry rule. A faithful
port of the previous app's `cross_sectional_ranking.py` (hypothesis
H-XSEC-S5-002). `features/multisectional/ranking.py`, pure Python. **SPY** is
the benchmark.

## Eligibility

`assets.active = 1`, each needs ≥ **220** adjusted-close bars ending on the
shared latest date. Return endpoints are aligned to **SPY session dates**
(look up the symbol's price on the exact SPY date; missing → that metric is
`null`). The leadership overlay needs ≥ 340 SPY sessions or it is skipped.

## Per-symbol technical-context row

| field | definition |
| --- | --- |
| `rs_3m / rs_6m / rs_12m` | own return over 63 / 126 / 252 sessions **minus** SPY's over the same span |
| `high_52w_distance` | `price / max(adj_close, 252) − 1` (0 = at the high) |
| `trend_distance` | mean of `ln(price / SMA_n)`, `n ∈ {20, 50, 100, 200}` |
| `slope` | mean of `SMA50 / SMA50₋₂₀ − 1` and `SMA200 / SMA200₋₂₀ − 1` |
| `above_all_mas` / `ordered_mas` | above every SMA 20/50/100/200 / a perfect `price>SMA20>…>SMA200` stack |
| `median_dollar_volume_21d` | median raw `close × volume`, last 21 bars |

**Composite score** = percentile-rank each metric across the eligible
universe, then a weighted mean of the *available* percentiles (missing
dropped, remainder renormalised), 0–100:
`rs_3m .25 · rs_6m .25 · rs_12m .15 · high_52w_distance .15 · trend_distance
.10 · slope .10`.

## Leadership overlay (H-XSEC-S5-002)

- **Formations** = the last **13 weekly** anchors (last session of each ISO
  week with index ≥ 252).
- Per formation, per eligible symbol (all 6 endpoints `0,−5,−21,−63,−126,−252`
  valid; raw close ≥ $5; 21 consecutive dollar-volume bars):
  `relative_strength` = own 63-session return − SPY's; `return_5d`.
- **Liquid pool** = top **100** by median 21-day dollar volume.
  **Leaders** = top decile of the liquid pool by `relative_strength`.
- `leadership_persistence` = (# of the 13 formations a name led) / 13;
  `candidate_weight` = Σ `1 / leader_count / n_formations` (a natural
  equal-weight average across the 13 sleeves — **not** an allocation).
- From the **latest formation only**: `liquidity_rank` (1–100),
  `rs_3m_percentile`, `current_leaders`, `return_5d`,
  `reversal_5d_percentile` (percentile of `−return_5d`),
  `sector_relative_return_5d` + `sector_relative_reversal_percentile`
  (sectors with ≥ 3 members — from `assets.sector`, populated by the
  memberships sync; ≈ 65 of the Top-100 get these).

**Rebound watch:** `is_reversal_watch = max(reversal_5d_percentile,
sector_relative_reversal_percentile) ≥ 90`. Gets **no** momentum weight — its
own table.

## Caching & API

`ranking_runs` (migration 0008) holds JSON snapshots, last 30 kept.

| Endpoint | |
| --- | --- |
| `GET /api/multisectional/ranking` | last snapshot (~50 ms) + `computed_at`, `newest_price_date`, `stale` (newer `price_bars` than the snapshot), or `status: "not_computed"` before the first recompute. |
| `POST /api/multisectional/ranking/recompute` | ~1–2 s compute over every eligible symbol, store, return. |

The page **never recomputes on load** — only the Recompute button (emphasised
when `stale`).

## Frontend

`MultisectionalPage.tsx`: summary strip · **Screen** dropdown (5: Liquid
Top-100 / Current leaders / Active 13-week sleeves / Above all MAs / All
eligible) · **Sort** dropdown (12: leadership persistence, 3M percentile,
candidate weight, liquidity rank, technical-context score, 3m/6m/12m vs SPY,
52w-high proximity, MA distance, MA slope, dollar volume) · symbol/company
search · a dense 15-column main table (symbol → `/timing/:symbol`) · the
rebound-watch table · methodology (disclosed weights) + source-inventory
panels.
