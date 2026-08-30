# Macro page

`/macro` — "risk-on or risk-off, right now?" Two independent readings over the
same `macro_observations`: a deterministic composite (always shown) and an
optional adversarial-LLM regime gauge (button). `features/macro/`.

## Naive composite — `composite.py`

Pure, disclosed, recomputed live per request (no persisted score).

- **`_SPECS: dict[series_id, FactorSpec]`** — one entry per scored series.
  `FactorSpec(feature, sign, confidence, rationale, caveat, two_sided)`.
  `feature ∈ {level, yoy, mom3}` (e.g. `FEDFUNDS` uses `mom3` — policy
  *direction*, not level). `sign` = +1 if higher ⇒ more risk-on, −1 if
  higher ⇒ more risk-off. Every sign is derived from the series'
  transmission mechanism, with `rationale` / `caveat` strings surfaced in the
  UI. **24 series scored** across inflation / rates / growth / labor / risk /
  money-fx. `DGS2` and `M2SL` are tracked but **not scored** (redundant /
  regime-unstable) and render as "not scored" cards.
- **Pipeline:** per series → signed z-score of the chosen feature over a
  trailing ~5y window → mean of the *available* signed contributions
  (equal-weight, stated as such) → logistic squash → **0–100** + a zone
  label.
- **Asymmetric clip** for `two_sided=True` factors (CPI ×4, WTI, DGS10,
  DTWEXBGS): the risk-off direction is uncapped (`RISK_OFF_FLOOR = −3.0`) but
  the "favourable" direction saturates at `FAVOURABLE_CAP = +1.0` — because
  disinflation-into-recession, an oil crash, a dollar collapse are
  ambiguous, not clean positives.
- `next_release_estimate` rolls the last observation date forward whole
  periods to the next future date ("next release ≈ N days / due").

## AI regime gauge — `macro/ai_regime/`

Optional. **Button-only**, cached once per `trading_date` (UNIQUE on
`ai_regime_runs`). The structural analysts use a **compact macro-financial
snapshot only** (no equities / crypto / gold): per-series feature vectors +
30/60-point arrays for the key rate/credit/vol series. The separate catalyst
overlay may web-search dated current events and market-pricing confirmation.

- **7 personas + a reconciler (medium/large).** `risk_on` / `risk_off` one-sided advocates;
  `inflation` / `credit_vol` / `growth_labor` / `rates_curve` neutral domain
  analysts; `macro_catalyst` is a separate web-searched event overlay, not a
  structural vote. Prompt text in `prompts.toml` (`version = 5`).
- **Rounds:** (1) independent persona votes; (2) advocates rebut each other
  (large budget only); (3) reconciler → holistic score + confidence.
- **Domain weights** (`prompts.toml [weights]`): base `credit_vol 0.30 /
  growth_labor 0.30 / inflation 0.20 / rates_curve 0.20`. The inflation
  weight scales `0.20 → 0.40` with `boost = clip(|corePCE_yoy − 2.0| / 2.0,
  0, 1)`; the others renormalise. (2022 showed inflation can dominate the
  risk regime via the discount-rate channel.)
- **Score blend:** `score_raw = 0.6 · code_weighted_score + 0.4 ·
  reconciler_score`. `code_weighted_score` is deterministic — `Σ weight ·
  conviction · signed_vote` over the neutral analysts (advocates excluded).
- **Macro catalyst overlay:** medium/large runs make one Responses API web-search
  call for material events from the last 7 days. It defaults to neutral, is
  excluded from structural tallies and weights, and is capped at ±5 before a
  deterministic confidence, already-priced, and 3-day half-life reduction.
  Mostly-priced or unsourced events contribute zero; unavailable web search
  degrades to neutral without failing the structural run.
- **Calibration (code, after the blend):** agreement ceiling,
  both-advocates-confident penalty, stale-input penalty
  (`2·period + typical_lag + 12` day threshold), naive-divergence penalty,
  vote-sanity, verbosity truncation. Stored as `score` / `confidence` vs the
  `_raw` values + `calibration_notes`.
- **Budgets** (`models.toml`): `small` (4 structural personas, features-only snapshot,
  700/1100 tok), `medium` (6 structural + catalyst, + key arrays, 900/1500),
  `large` (6 structural + catalyst, + history,
  1200/2200 + rebuttal round). Model list from the OpenAI account, seeded
  ids in `model_catalog.py`. Reasoning models retry once at 4× tokens if the
  first response is empty.

## API

| Endpoint | |
| --- | --- |
| `GET /api/macro/overview` | composite (0–100 + zone + per-factor z/sign/contribution/rationale) + 6 category grids, each series: last-10 spark, 1m/12m change, next-release estimate. |
| `GET /api/macro/ai-regime/models` · `/models/account` · `/budgets` | selectable models + budget presets. |
| `POST /api/macro/ai-regime/run` `{model?, budget?, force?}` | blocking ~10–40 s, cached per trading date. |
| `GET /api/macro/ai-regime/latest` · `/history` | last run / history. |

## Frontend

`MacroPage.tsx`: **`CompositeReadout`** (full-width — 0–100 + zone chip +
collapsible per-factor table + a deterministic plain-language reading naming
the top ± contributors, no AI) · **`RegimePanel`** (full-width — `@mui/x-charts`
Gauge, calibration line, meta, expandable per-analyst votes/reasoning,
"AI may be wrong" disclaimer; the model/budget/Run controls sit behind a
"Re-run / model" toggle, dashboard always visible) · category grids of
`MacroCard` sparklines coloured by composite contribution sign.
