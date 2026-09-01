"""Builds the Macro page overview payload from the DB (no fetching)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict

from app.features.macro import composite as comp

_CATEGORY_LABELS = {
    "inflation": "Inflation",
    "rates": "Rates",
    "growth": "Growth",
    "labor": "Employment",
    "risk": "Risk",
    "money-fx": "Money & FX",
}
_CATEGORY_ORDER = ["inflation", "rates", "growth", "labor", "risk", "money-fx"]

SPARK_POINTS = 10


def _all_obs(conn: sqlite3.Connection) -> dict[str, list[tuple[str, float]]]:
    rows = conn.execute(
        "SELECT series_id, date, value FROM macro_observations "
        "WHERE value IS NOT NULL ORDER BY series_id, date"
    ).fetchall()
    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        out.setdefault(r["series_id"], []).append((r["date"], r["value"]))
    return out


def _composite_reading(composite, labels: dict[str, str]) -> str:
    """A deterministic plain-language read — names the biggest risk-on and
    risk-off pulls. No AI."""
    used = [f for f in composite.factors if f.contribution is not None]
    if not used or composite.score is None:
        return "Not enough history to compute a composite yet."
    used.sort(key=lambda f: f.contribution, reverse=True)
    pos = [f for f in used if f.contribution > 0.15][:3]
    neg = [f for f in used if f.contribution < -0.15][-3:][::-1]

    def phrase(fs):
        return ", ".join(f"{labels.get(f.series_id, f.series_id)} (z {f.z:+.1f})" for f in fs)

    zone = composite.zone
    lead = {
        "risk-on": f"The naive composite reads risk-ON ({composite.score}).",
        "risk-off": f"The naive composite reads risk-OFF ({composite.score}).",
        "neutral": f"The naive composite is roughly neutral ({composite.score}).",
    }[zone]
    parts = [lead]
    if pos:
        parts.append(f"Biggest risk-on pulls: {phrase(pos)}.")
    if neg:
        parts.append(f"Biggest risk-off pulls: {phrase(neg)}.")
    parts.append(f"{composite.n_used} series, equal-weighted. Not validated.")
    return " ".join(parts)


def build_overview(conn: sqlite3.Connection) -> dict:
    catalog = conn.execute(
        """
        SELECT c.series_id, c.title, c.short_label, c.category, c.frequency,
               c.units_short, c.typical_lag_days, s.last_date, s.last_value,
               s.point_count
          FROM macro_series_catalog c
          LEFT JOIN macro_obs_stats s ON s.series_id = c.series_id
         WHERE c.tracked = 1
        """
    ).fetchall()

    obs = _all_obs(conn)
    as_of = max((r["last_date"] for r in catalog if r["last_date"]), default=None)
    freqs = {r["series_id"]: r["frequency"] for r in catalog}

    composite = comp.compute(obs, freqs, as_of)
    contrib_by_id = {f.series_id: f for f in composite.factors}
    label_by_id = {r["series_id"]: (r["short_label"] or r["title"] or r["series_id"]) for r in catalog}
    reading = _composite_reading(composite, label_by_id)

    cats: dict[str, list[dict]] = {k: [] for k in _CATEGORY_ORDER}
    for r in catalog:
        sid = r["series_id"]
        series_obs = obs.get(sid) or []
        spark = series_obs[-SPARK_POINTS:]
        est_date, in_days = comp.next_release_estimate(
            r["frequency"], r["last_date"], r["typical_lag_days"] or 14
        )
        change_1m = change_12m = None
        vals = [v for _, v in series_obs]
        per_year = comp._OBS_PER_YEAR[comp._freq_key(r["frequency"])]
        m_step = max(1, round(per_year / 12))  # ~one month of observations
        y_step = max(1, per_year)              # ~one year
        if len(vals) > m_step and vals[-1 - m_step]:
            change_1m = round((vals[-1] / vals[-1 - m_step] - 1) * 100, 3)
        if len(vals) > y_step and vals[-1 - y_step]:
            change_12m = round((vals[-1] / vals[-1 - y_step] - 1) * 100, 3)

        f = contrib_by_id.get(sid)
        cats.setdefault(r["category"], []).append(
            {
                "series_id": sid,
                "label": r["short_label"] or r["title"] or sid,
                "units_short": r["units_short"],
                "frequency": r["frequency"],
                "point_count": r["point_count"] or 0,
                "latest_value": r["last_value"],
                "latest_date": r["last_date"],
                "spark": [{"date": d, "value": v} for d, v in spark],
                "change_1m_pct": change_1m,
                "change_12m_pct": change_12m,
                "next_release_estimate": est_date,
                "next_release_in_days": in_days,
                "composite_feature": f.feature if f else None,
                "composite_sign": f.sign if f else None,
                "composite_confidence": f.confidence if f else None,
                "composite_rationale": f.rationale if f else None,
                "composite_caveat": (f.caveat or None) if f else None,
                "composite_z": (round(f.z, 3) if f and f.z is not None else None),
                "composite_window_years": (f.window_years if f else None),
                "composite_short_window": (f.short_window if f else None),
                "composite_contribution": (
                    round(f.contribution, 3) if f and f.contribution is not None else None
                ),
            }
        )

    return {
        "as_of": as_of,
        "composite": {
            "score": composite.score,
            "zone": composite.zone,
            "n_used": composite.n_used,
            "reading": reading,
            "window_years": comp.Z_WINDOW_YEARS,
            "note": (
                f"Naive, equal-weight, hand-assigned signs; robust median/MAD z "
                f"vs a fixed {comp.Z_WINDOW_YEARS:g}-year window. Not validated."
            ),
        },
        "categories": [
            {"key": k, "label": _CATEGORY_LABELS[k], "series": cats.get(k, [])}
            for k in _CATEGORY_ORDER
            if cats.get(k)
        ],
        "factors": [asdict(f) for f in composite.factors],
    }
