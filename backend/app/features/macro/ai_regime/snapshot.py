"""Compact snapshot builder for the AI regime run.

**Macro-financial series only.** Sends *derived features* per series (not raw
arrays) plus short trajectory arrays for a handful of rate/credit/vol/oil
series where the path matters. Deliberately excludes equity-index / sector /
single-stock / crypto price action — that reasoning belongs to the
Trend/Timing pages, not the macro regime read.
See docs/draft-design/10-macro-page-and-ai-regime.md §5.
"""

from __future__ import annotations

import json
import math
import sqlite3

# Series whose *shape* matters — get a trajectory array (budget-controlled length).
KEY_SERIES = [
    "DGS2", "DGS10", "DGS30", "T10Y2Y", "T10Y3M", "T10YIE",
    "BAMLH0A0HYM2", "VIXCLS", "NFCI", "DCOILWTICO",
]

# Rough #observations for 1m/3m/6m/12m by frequency.
_STEPS = {
    "Daily": (21, 63, 126, 252),
    "Weekly": (4, 13, 26, 52),
    "Monthly": (1, 3, 6, 12),
    "Quarterly": (1, 1, 2, 4),
}


def _round(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(x, n)


def _pct_change(vals: list[float], step: int) -> float | None:
    if len(vals) <= step or vals[-1 - step] == 0:
        return None
    return (vals[-1] / vals[-1 - step] - 1.0) * 100.0


def _abs_change(vals: list[float], step: int) -> float | None:
    if len(vals) <= step:
        return None
    return vals[-1] - vals[-1 - step]


def _z_and_pctile(vals: list[float], window: int) -> tuple[float | None, int | None]:
    if len(vals) < 12:
        return None, None
    tail = vals[-window:] if len(vals) > window else vals
    mu = sum(tail) / len(tail)
    var = sum((x - mu) ** 2 for x in tail) / (len(tail) - 1)
    sd = math.sqrt(var)
    z = 0.0 if sd == 0 else (vals[-1] - mu) / sd
    below = sum(1 for x in tail if x <= vals[-1])
    return round(z, 2), round(100 * below / len(tail))


def _trend_word(vals: list[float]) -> str:
    if len(vals) < 6:
        return "flat"
    seg = vals[-6:]
    mu = sum(seg) / len(seg)
    sd = math.sqrt(sum((x - mu) ** 2 for x in seg) / (len(seg) - 1)) or 1e-9
    delta = (seg[-1] - seg[0]) / sd
    if delta > 0.6:
        return "rising"
    if delta < -0.6:
        return "falling"
    return "flat"


def _macro_features(conn: sqlite3.Connection) -> tuple[dict, str | None]:
    cat_rows = conn.execute(
        "SELECT series_id, short_label, category, frequency, units_short "
        "FROM macro_series_catalog WHERE tracked = 1 ORDER BY category, series_id"
    ).fetchall()
    obs_rows = conn.execute(
        "SELECT series_id, date, value FROM macro_observations "
        "WHERE value IS NOT NULL ORDER BY series_id, date"
    ).fetchall()
    by_series: dict[str, list[tuple[str, float]]] = {}
    for r in obs_rows:
        by_series.setdefault(r["series_id"], []).append((r["date"], r["value"]))

    out: dict[str, dict] = {}
    as_of: str | None = None
    for r in cat_rows:
        sid = r["series_id"]
        series = by_series.get(sid) or []
        if not series:
            continue
        vals = [v for _, v in series]
        last_date = series[-1][0]
        as_of = max(as_of, last_date) if as_of else last_date
        s1, s3, s6, s12 = _STEPS.get((r["frequency"] or "").strip(), (1, 3, 6, 12))
        # rates/spreads/indices: report absolute change; index levels: % change.
        use_abs = sid in KEY_SERIES or sid in ("FEDFUNDS", "UNRATE", "UMCSENT")
        chg = _abs_change if use_abs else _pct_change
        z, pctile = _z_and_pctile(vals, 5 * 252)
        out[sid] = {
            "label": r["short_label"] or sid,
            "cat": r["category"],
            "unit": r["units_short"],
            "latest": _round(vals[-1], 4),
            "as_of": last_date,
            ("d1m_abs" if use_abs else "d1m_pct"): _round(chg(vals, s1)),
            ("d3m_abs" if use_abs else "d3m_pct"): _round(chg(vals, s3)),
            ("d12m_abs" if use_abs else "d12m_pct"): _round(chg(vals, s12)),
            "z_5y": z,
            "pctile_5y": pctile,
            "trend": _trend_word(vals),
        }
    return out, as_of


def _key_arrays(conn: sqlite3.Connection, n: int) -> dict:
    if n <= 0:
        return {}
    out: dict[str, list[float]] = {}
    for sid in KEY_SERIES:
        rows = conn.execute(
            "SELECT value FROM macro_observations WHERE series_id = ? AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT ?",
            (sid, n),
        ).fetchall()
        if rows:
            out[sid] = [round(r["value"], 3) for r in reversed(rows)]
    return out


def build_snapshot(conn: sqlite3.Connection, *, detail: str, rate_series_points: int) -> tuple[dict, str]:
    """Returns (snapshot_dict, snapshot_json_string). Macro-financial only —
    no equity/sector/stock/crypto price action."""
    features, as_of = _macro_features(conn)
    snap: dict = {"as_of": as_of, "macro": features}

    if detail in ("features_plus_key_arrays", "features_plus_arrays_plus_history"):
        arrays = _key_arrays(conn, rate_series_points)
        if arrays:
            snap["macro_paths"] = arrays
    if detail == "features_plus_arrays_plus_history":
        # last 12 raw obs for every series
        hist: dict[str, list[float]] = {}
        for sid in features:
            rows = conn.execute(
                "SELECT value FROM macro_observations WHERE series_id = ? AND value IS NOT NULL "
                "ORDER BY date DESC LIMIT 12",
                (sid,),
            ).fetchall()
            hist[sid] = [round(r["value"], 4) for r in reversed(rows)]
        snap["macro_recent"] = hist

    js = json.dumps(snap, separators=(",", ":"))
    return snap, js
