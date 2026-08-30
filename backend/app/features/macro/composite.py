"""Naive risk-on/off composite (the non-AI baseline for the Macro page).

Fully disclosed, hand-assigned, equal-weight — labeled "naive, not validated"
on the page. See docs/draft-design/10-macro-page-and-ai-regime.md §3 and the
per-indicator sign audit in §3.1.

For each series we pick a *feature* (level, YoY %, or 3-month change),
standardise the latest value against the trailing window, apply a
hand-assigned risk-on sign (+1 = risk-on, i.e. higher-feature ⇒ risk-on),
average the signed z-scores, and squash to 0-100 with a logistic.

Each entry carries a one-line `rationale` (the transmission mechanism) and a
`confidence` — surfaced on the card so the sign is auditable, not a black box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

# feature: "level" | "yoy" (12-obs % change) | "mom3" (3-obs change of the level)


@dataclass(frozen=True)
class FactorSpec:
    feature: str
    sign: int          # +1 risk-on, -1 risk-off
    confidence: str     # "high" | "medium" | "low"
    rationale: str      # why this sign — the transmission mechanism
    caveat: str = ""    # when it can flip / why it's imperfect
    two_sided: bool = False  # a big move the "favourable" way is ambiguous
                             # (disinflation-into-recession, oil demand collapse,
                             #  dollar loss-of-faith) → cap that contribution.


# Asymmetric clip for `two_sided` factors: the risk-off direction is
# uncapped, the "favourable" direction saturates at +FAVOURABLE_CAP.
FAVOURABLE_CAP = 1.0
RISK_OFF_FLOOR = -3.0


_SPECS: dict[str, FactorSpec] = {
    # ---- Risk gauges (clean, monotonic, no "good news is bad news") ----
    "VIXCLS": FactorSpec(
        "level", -1, "high",
        "Direct fear gauge: higher implied vol = less risk appetite.",
    ),
    "BAMLH0A0HYM2": FactorSpec(
        "level", -1, "high",
        "Wider high-yield credit spread = higher default-risk premium = risk-off; "
        "spreads widen into every drawdown/recession.",
    ),
    "NFCI": FactorSpec(
        "level", -1, "high",
        "NFCI is built so positive = tighter-than-average financial conditions; "
        "tighter = risk-off.",
    ),
    "STLFSI4": FactorSpec(
        "level", -1, "high",
        "Financial-stress index: zero = normal, higher = more system stress = risk-off.",
    ),
    # ---- Yield curve (well established) ----
    "T10Y2Y": FactorSpec(
        "level", +1, "high",
        "An inverted (negative) 10y-2y precedes recessions; a positive / steepening "
        "spread signals a healthier expansion.",
        "A bear-steepener (long rates spiking) can be risk-off despite a rising spread.",
    ),
    "T10Y3M": FactorSpec(
        "level", +1, "high",
        "The 10y-3m spread is the Fed's preferred recession predictor; inversion = "
        "warning, positive = benign.",
    ),
    # ---- Labour stress (clean; the Fed does not *want* higher unemployment) ----
    "UNRATE": FactorSpec(
        "mom3", -1, "high",
        "A rising unemployment rate is risk-off in every regime; the *change* (Sahm "
        "rule) is one of the best real-time recession signals.",
    ),
    "ICSA": FactorSpec(
        "mom3", -1, "high",
        "Rising initial jobless claims = layoffs accelerating = labour market cracking. "
        "High-frequency leading indicator.",
    ),
    # ---- Growth / activity (dominant effect = expansion is good) ----
    "GDPC1": FactorSpec(
        "yoy", +1, "medium",
        "Faster real GDP growth = expansion & earnings growth = risk-on; contraction = "
        "recession = risk-off.",
        "Above-trend growth in an overheating regime can be net risk-off via a hawkish Fed.",
    ),
    "INDPRO": FactorSpec(
        "yoy", +1, "high",
        "Coincident cyclical gauge: rising industrial production = expansion; a "
        "manufacturing recession = risk-off.",
    ),
    "RSAFS": FactorSpec(
        "yoy", +1, "medium",
        "Consumer-demand health: rising retail sales = expansion; collapsing = recession.",
        "Red-hot retail sales in an inflation fight is mild 'good news is bad news'.",
    ),
    "HOUST": FactorSpec(
        "yoy", +1, "high",
        "Housing leads the business cycle; rising starts = confidence + easy credit, "
        "collapsing starts = classic recession lead.",
    ),
    "UMCSENT": FactorSpec(
        "level", +1, "medium",
        "Higher consumer sentiment = more willingness to spend = risk-on.",
        "At extreme lows sentiment can be contrarian (capitulation).",
    ),
    "PAYEMS": FactorSpec(
        "mom3", +1, "low",
        "Over the cycle, faster payroll growth = expansion and job losses define "
        "recessions, so accelerating payrolls = risk-on / decelerating = risk-off.",
        "The clearest 'good news is bad news' case: in a tight-labour, above-target-"
        "inflation regime a hot print keeps the Fed hawkish and can be risk-off short-term.",
    ),
    # ---- Inflation (correct for an above-target regime; truly U-shaped) ----
    "CPIAUCSL": FactorSpec(
        "yoy", -1, "medium",
        "With inflation above target, higher / rising inflation ⇒ a more hawkish Fed ⇒ "
        "multiple compression and recession risk = risk-off.",
        "U-shaped, not linear: deflation / disinflation-into-recession is also risk-off. "
        "The favourable (cooling) side of the contribution is capped for that reason.",
        two_sided=True,
    ),
    "CPILFESL": FactorSpec(
        "yoy", -1, "medium",
        "Core CPI drives Fed policy; hotter core = tighter policy = risk-off in the "
        "current regime.",
        "Same U-shape caveat as headline CPI; cooling side capped.",
        two_sided=True,
    ),
    "PCEPI": FactorSpec(
        "yoy", -1, "medium",
        "The Fed's headline inflation target measure; hotter = risk-off while above 2%.",
        "U-shaped; deflation is also risk-off; cooling side capped.",
        two_sided=True,
    ),
    "PCEPILFE": FactorSpec(
        "yoy", -1, "medium",
        "The Fed's core target measure; the single most policy-relevant inflation gauge. "
        "Hotter = risk-off above target.",
        "U-shaped; cooling side capped.",
        two_sided=True,
    ),
    "DCOILWTICO": FactorSpec(
        "level", -1, "medium",
        "An oil spike raises headline inflation and input costs, drains consumer "
        "purchasing power, and has preceded most post-war recessions.",
        "Two-sided: moderate oil strength with strong global demand can be 'risk-on "
        "reflation'; oil crashes can be demand collapse (risk-off). Falling side capped.",
        two_sided=True,
    ),
    # ---- Rates: use the *direction* (hiking / rising = tightening), not the level ----
    "FEDFUNDS": FactorSpec(
        "mom3", -1, "medium",
        "A rising policy rate = active tightening = headwind for risk assets. Using the "
        "3-month change (hiking vs cutting), not the level, which is non-monotonic.",
    ),
    "DGS10": FactorSpec(
        "mom3", -1, "medium",
        "A rapidly *rising* 10y tightens financial conditions (mortgages, corporate "
        "borrowing, equity discount rate); the 2022-23 selloffs were yield-driven.",
        "A rising 10y can also be 'good' reflation; a falling 10y is classic "
        "flight-to-quality. Direction-dependent; falling side capped.",
        two_sided=True,
    ),
    "MORTGAGE30US": FactorSpec(
        "mom3", -1, "medium",
        "Rising mortgage rates = housing headwind + negative wealth effect + tighter "
        "consumer conditions.",
        "Largely tracks the 10y (some redundancy).",
    ),
    # ---- Money / liquidity / FX ----
    # M2SL dropped from the composite (kept as a card): its sign is
    # regime-unstable — +1 "worked" in 2020-21, then inverted in 2022-23 when
    # M2 growth turned negative while equities rose. Liquidity is measured
    # better by WALCL + NFCI + STLFSI4.
    "WALCL": FactorSpec(
        "yoy", +1, "medium",
        "'Don't fight the Fed': balance-sheet expansion (QE) injects liquidity = risk-on; "
        "QT drains it (2018, 2022 selloffs).",
        "Emergency expansions happen *during* crises (2008, Mar-2020, Mar-2023), so a "
        "sudden spike can coincide with acute risk-off.",
    ),
    "DTWEXBGS": FactorSpec(
        "mom3", -1, "medium",
        "A rapidly strengthening dollar tightens global conditions (dollar funding), "
        "hurts US multinational earnings and EM — the 'dollar wrecking ball' (2015, 2022).",
        "The dollar is also a safe haven, so it can rise *because of* risk-off. "
        "The weakening side is capped.",
        two_sided=True,
    ),
}

Z_WINDOW_YEARS = 5
K = 1.0  # logistic steepness


@dataclass
class Factor:
    series_id: str
    feature: str
    sign: int
    confidence: str
    rationale: str
    caveat: str
    z: float | None
    contribution: float | None  # signed z, or None if not enough data


@dataclass
class Composite:
    score: float | None
    zone: str
    factors: list[Factor]
    n_used: int


def _feature_series(obs: list[tuple[str, float]], feature: str) -> list[float]:
    vals = [v for _, v in obs]
    if feature == "level":
        return vals
    if feature == "yoy":
        out = []
        for i in range(12, len(vals)):
            prev = vals[i - 12]
            out.append((vals[i] / prev - 1.0) * 100.0 if prev else 0.0)
        return out
    if feature == "mom3":
        step = 3
        return [vals[i] - vals[i - step] for i in range(step, len(vals))]
    return vals


def _zscore(series: list[float], window: int) -> float | None:
    if len(series) < 8:
        return None
    tail = series[-window:] if len(series) > window else series
    mu = sum(tail) / len(tail)
    var = sum((x - mu) ** 2 for x in tail) / (len(tail) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (series[-1] - mu) / sd


def _zone(score: float) -> str:
    if score < 40:
        return "risk-off"
    if score < 60:
        return "neutral"
    return "risk-on"


def compute(observations: dict[str, list[tuple[str, float]]], latest_date: str | None) -> Composite:
    factors: list[Factor] = []
    signed: list[float] = []

    for series_id, spec in _SPECS.items():
        obs = observations.get(series_id) or []
        feat = _feature_series(obs, spec.feature)
        z = _zscore(feat, Z_WINDOW_YEARS * 252)
        contrib = None if z is None else spec.sign * z
        if contrib is not None and spec.two_sided:
            # risk-off direction uncapped; "favourable" direction saturates
            contrib = max(RISK_OFF_FLOOR, min(contrib, FAVOURABLE_CAP))
        factors.append(
            Factor(
                series_id, spec.feature, spec.sign, spec.confidence, spec.rationale,
                spec.caveat, z, contrib,
            )
        )
        if contrib is not None:
            signed.append(contrib)

    if not signed:
        return Composite(None, "neutral", factors, 0)

    raw = sum(signed) / len(signed)
    score = 100.0 / (1.0 + math.exp(-K * raw))
    return Composite(round(score, 1), _zone(score), factors, len(signed))


def spec_for(series_id: str) -> FactorSpec | None:
    return _SPECS.get(series_id)


def next_release_estimate(
    frequency: str | None, last_obs: str | None, typical_lag_days: int
) -> tuple[str | None, int | None]:
    if not last_obs:
        return None, None
    try:
        d = date.fromisoformat(last_obs)
    except ValueError:
        return None, None
    period = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Quarterly": 91}.get(
        (frequency or "").strip(), 30
    )
    est = d + timedelta(days=period + max(0, typical_lag_days))
    today = date.today()
    if est < today:
        periods_behind = (today - est).days // period + 1
        est += timedelta(days=period * periods_behind)
    return est.isoformat(), (est - today).days
