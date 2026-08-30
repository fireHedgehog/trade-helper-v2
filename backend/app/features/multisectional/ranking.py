"""Cross-sectional ranking — a faithful port of the old app's
`cross_sectional_ranking.py`, adapted to this app's schema.

Pure price/volume. Computed live from `price_bars` on each request (no
persisted ranking table — same reasoning as the Macro composite). SPY is the
benchmark. Every metric is descriptive research, not validated alpha.

Data-gap note: the sector-relative reversal signals need a per-symbol sector
tag. This app's `assets.sector` / `symbol_memberships` are not populated yet
(the memberships scrape — Wikipedia S&P 500 GICS + SSGA sector-SPDR holdings —
is designed in `docs/draft-design/09-…-audit.md §4.2` but not built). Until
then those two columns come back NULL. Everything else works.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import date
from typing import Any

LEADERSHIP_WEEKS = 13
LEADERSHIP_LOOKBACK = 63
LIQUID_POOL_SIZE = 100
MIN_RAW_PRICE = 5.0
MIN_MATURE_HISTORY = 252
MIN_ROW_HISTORY = 220
BARS_PER_SYMBOL = 420          # enough for SMA200 + 52w high + 13 weekly formations
SECTOR_ANCHORS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")

COMPOSITE_WEIGHTS = {
    "rs_3m": 0.25, "rs_6m": 0.25, "rs_12m": 0.15,
    "high_52w_distance": 0.15, "trend_distance": 0.10, "slope": 0.10,
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _percentiles(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    pairs = sorted((float(row[key]), row["symbol"]) for row in rows if row.get(key) is not None)
    if not pairs:
        return {}
    if len(pairs) == 1:
        return {pairs[0][1]: 50.0}
    result: dict[str, float] = {}
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        percentile = ((index + end - 1) / 2) / (len(pairs) - 1) * 100
        for _, symbol in pairs[index:end]:
            result[symbol] = percentile
        index = end
    return result


def _weekly_formations(dates: list[str], count: int = LEADERSHIP_WEEKS) -> list[int]:
    last_by_week: dict[tuple[int, int], int] = {}
    for index, value in enumerate(dates):
        iso = date.fromisoformat(value).isocalendar()
        last_by_week[(iso[0], iso[1])] = index
    mature = [index for index in last_by_week.values() if index >= MIN_MATURE_HISTORY]
    return sorted(mature)[-count:]


def _leadership_overlay(
    dates: list[str],
    spy_by_date: dict[str, float],
    histories: dict[str, dict[str, dict[str, float | None]]],
    sector_by_symbol: dict[str, str],
) -> dict[str, Any]:
    formations = _weekly_formations(dates)
    selections: list[list[str]] = []
    current_liquidity_rank: dict[str, int] = {}
    current_percentile: dict[str, float] = {}
    current_leaders: set[str] = set()
    current_reversal_return: dict[str, float] = {}
    current_reversal_percentile: dict[str, float] = {}
    current_sector_relative: dict[str, float] = {}
    current_sector_reversal_percentile: dict[str, float] = {}

    for formation in formations:
        endpoint_indices = (formation, formation - 5, formation - 21, formation - 63,
                            formation - 126, formation - 252)
        if endpoint_indices[-1] < 0 or formation - LEADERSHIP_LOOKBACK < 0:
            continue
        endpoint_dates = [dates[i] for i in endpoint_indices]
        formation_date = dates[formation]
        lookback_date = dates[formation - LEADERSHIP_LOOKBACK]
        volume_dates = dates[formation - 20: formation + 1]
        spy_now = spy_by_date.get(formation_date)
        spy_then = spy_by_date.get(lookback_date)
        if spy_now is None or spy_then is None or spy_now <= 0 or spy_then <= 0:
            continue
        spy_return = spy_now / spy_then - 1.0

        eligible: list[tuple[str, float, float, float]] = []
        for symbol, history in histories.items():
            endpoints = [history.get(day) for day in endpoint_dates]
            if any(it is None or it.get("price") is None or float(it["price"]) <= 0 for it in endpoints):
                continue
            current = history.get(formation_date)
            raw_close = current.get("raw_close") if current else None
            if raw_close is None or float(raw_close) < MIN_RAW_PRICE:
                continue
            dollar_volume: list[float] = []
            for day in volume_dates:
                item = history.get(day)
                if item is None or item.get("raw_close") is None or item.get("volume") is None:
                    dollar_volume = []
                    break
                raw, volume = float(item["raw_close"]), float(item["volume"])
                if raw <= 0 or volume <= 0:
                    dollar_volume = []
                    break
                dollar_volume.append(raw * volume)
            if len(dollar_volume) != 21:
                continue
            own_now = float(history[formation_date]["price"])
            own_then = float(history[lookback_date]["price"])
            relative_strength = own_now / own_then - 1.0 - spy_return
            return_5d = own_now / float(history[endpoint_dates[1]]["price"]) - 1.0
            median_dollar_volume = sorted(dollar_volume)[len(dollar_volume) // 2]
            eligible.append((symbol, median_dollar_volume, relative_strength, return_5d))

        liquid = sorted(eligible, key=lambda it: (-it[1], it[0]))[:LIQUID_POOL_SIZE]
        if not liquid:
            continue
        relative_rows = [{"symbol": s, "rs_3m": v} for s, _, v, _ in liquid]
        percentiles = _percentiles(relative_rows, "rs_3m")
        leader_count = max(1, len(liquid) // 10)
        leaders = [s for s, _, _, _ in sorted(liquid, key=lambda it: (-it[2], it[0]))[:leader_count]]
        selections.append(leaders)

        if formation == formations[-1]:
            current_liquidity_rank = {s: i for i, (s, _, _, _) in enumerate(liquid, 1)}
            current_percentile = percentiles
            current_leaders = set(leaders)
            reversal_rows = [{"symbol": s, "reversal_5d": -r5} for s, _, _, r5 in liquid]
            current_reversal_return = {s: r5 for s, _, _, r5 in liquid}
            current_reversal_percentile = _percentiles(reversal_rows, "reversal_5d")

            sector_members: dict[str, list[tuple[str, float]]] = {}
            for s, _, _, r5 in liquid:
                sec = sector_by_symbol.get(s)
                if sec:
                    sector_members.setdefault(sec, []).append((s, r5))
            sector_relative_rows: list[dict[str, Any]] = []
            current_sector_relative = {}
            for members in sector_members.values():
                if len(members) < 3:
                    continue
                sector_mean = _mean([v for _, v in members])
                for s, v in members:
                    rel = v - sector_mean
                    current_sector_relative[s] = rel
                    sector_relative_rows.append({"symbol": s, "sector_relative_reversal": -rel})
            current_sector_reversal_percentile = _percentiles(
                sector_relative_rows, "sector_relative_reversal"
            )

    appearances = Counter(s for sel in selections for s in sel)
    sleeve_weights: Counter[str] = Counter()
    if selections:
        for sel in selections:
            for s in sel:
                sleeve_weights[s] += 1.0 / len(sel) / len(selections)
    return {
        "formation_count": len(selections),
        "liquidity_rank": current_liquidity_rank,
        "rs_3m_percentile": current_percentile,
        "current_leaders": current_leaders,
        "appearances": appearances,
        "persistence": {s: c / len(selections) for s, c in appearances.items()} if selections else {},
        "candidate_weight": dict(sleeve_weights),
        "return_5d": current_reversal_return,
        "reversal_5d_percentile": current_reversal_percentile,
        "sector_relative_return_5d": current_sector_relative,
        "sector_relative_reversal_percentile": current_sector_reversal_percentile,
    }


def compute_ranking(conn: sqlite3.Connection) -> dict[str, Any]:
    members = conn.execute(
        "SELECT symbol, name, sector, asset_class FROM assets WHERE active = 1 ORDER BY symbol"
    ).fetchall()
    member_syms = [m["symbol"] for m in members]
    name_by = {m["symbol"]: m["name"] for m in members}
    sector_by_symbol: dict[str, str] = {
        m["symbol"]: (m["sector"] or "") for m in members if m["sector"]
    }
    category_by = {m["symbol"]: (m["sector"] or m["asset_class"] or "equity") for m in members}

    # SPY benchmark (must be deep enough).
    spy_rows = conn.execute(
        "SELECT date, adj_close FROM price_bars WHERE symbol = 'SPY' AND adj_close IS NOT NULL "
        "ORDER BY date DESC LIMIT ?",
        (BARS_PER_SYMBOL,),
    ).fetchall()
    spy_history = list(reversed(spy_rows))
    spy_dates = [r["date"] for r in spy_history]
    spy_by_date = {r["date"]: float(r["adj_close"]) for r in spy_history}

    # Per-symbol bars in one sweep.
    if member_syms:
        ph = ",".join("?" for _ in member_syms)
        cutoff = spy_dates[0] if spy_dates else "2000-01-01"
        raw = conn.execute(
            f"""
            SELECT symbol, date, adj_close AS price, close AS raw_close, volume
              FROM price_bars
             WHERE symbol IN ({ph}) AND date >= ? AND adj_close IS NOT NULL
          ORDER BY symbol, date
            """,
            (*member_syms, cutoff),
        ).fetchall()
    else:
        raw = []
    bars: dict[str, list[sqlite3.Row]] = {}
    for b in raw:
        bars.setdefault(b["symbol"], []).append(b)

    latest_counts = Counter(h[-1]["date"] for h in bars.values() if h)
    latest = max(latest_counts, key=lambda d: (latest_counts[d], d)) if latest_counts else None

    histories: dict[str, dict[str, dict[str, float | None]]] = {}
    for sym, h in bars.items():
        if not h or h[-1]["date"] != latest:
            continue
        histories[sym] = {
            r["date"]: {
                "price": float(r["price"]),
                "raw_close": float(r["raw_close"]) if r["raw_close"] is not None else None,
                "volume": float(r["volume"]) if r["volume"] is not None else None,
            }
            for r in h
        }

    have_spy = len(spy_dates) >= 340
    leadership = (
        _leadership_overlay(spy_dates, spy_by_date, histories, sector_by_symbol)
        if have_spy
        else {
            "formation_count": 0, "liquidity_rank": {}, "rs_3m_percentile": {},
            "current_leaders": set(), "appearances": {}, "persistence": {},
            "candidate_weight": {}, "return_5d": {}, "reversal_5d_percentile": {},
            "sector_relative_return_5d": {}, "sector_relative_reversal_percentile": {},
        }
    )

    spy_returns: dict[int, float | None] = {}
    for period in (63, 126, 252):
        if len(spy_dates) <= period:
            spy_returns[period] = None
            continue
        then, now = spy_by_date[spy_dates[-1 - period]], spy_by_date[spy_dates[-1]]
        spy_returns[period] = now / then - 1.0 if then > 0 else None

    rows: list[dict[str, Any]] = []
    for sym in member_syms:
        h = bars.get(sym, [])
        if not h or h[-1]["date"] != latest:
            continue
        values = [float(b["price"]) for b in h]
        if len(values) < MIN_ROW_HISTORY:
            continue
        current = values[-1]
        by_date = histories.get(sym, {})
        sma20, sma50, sma100, sma200 = (_mean(values[-p:]) for p in (20, 50, 100, 200))
        prior_sma50 = _mean(values[-70:-20])
        prior_sma200 = _mean(values[-220:-20])
        rs: dict[int, float | None] = {}
        for period in (63, 126, 252):
            lb_date = spy_dates[-1 - period] if len(spy_dates) > period else None
            past = by_date.get(lb_date or "", {}).get("price")
            own = current / float(past) - 1.0 if past is not None and float(past) > 0 else None
            bench = spy_returns[period]
            rs[period] = own - bench if own is not None and bench is not None else None
        high_window = max(values[-252:])
        liquid_dv = [
            float(b["raw_close"]) * float(b["volume"])
            for b in h[-21:] if b["raw_close"] and b["volume"]
        ]
        rows.append({
            "symbol": sym, "name": name_by.get(sym), "category": category_by.get(sym),
            "as_of": h[-1]["date"], "price": current,
            "rs_3m": rs[63], "rs_6m": rs[126], "rs_12m": rs[252],
            "high_52w_distance": current / high_window - 1,
            "trend_distance": _mean([math.log(current / a) for a in (sma20, sma50, sma100, sma200)]),
            "slope": _mean([sma50 / prior_sma50 - 1, sma200 / prior_sma200 - 1]),
            "above_all_mas": current > sma20 and current > sma50 and current > sma100 and current > sma200,
            "ordered_mas": current > sma20 > sma50 > sma100 > sma200,
            "median_dollar_volume_21d": sorted(liquid_dv)[len(liquid_dv) // 2] if liquid_dv else None,
            "liquidity_rank": leadership["liquidity_rank"].get(sym),
            "is_liquid_top100": sym in leadership["liquidity_rank"],
            "rs_3m_percentile": leadership["rs_3m_percentile"].get(sym),
            "is_current_leader": sym in leadership["current_leaders"],
            "leadership_appearances_13w": leadership["appearances"].get(sym, 0) if leadership["formation_count"] else None,
            "leadership_persistence": leadership["persistence"].get(sym, 0.0) if leadership["formation_count"] else None,
            "candidate_weight": leadership["candidate_weight"].get(sym, 0.0) if leadership["formation_count"] else None,
            "return_5d": leadership["return_5d"].get(sym),
            "reversal_5d_percentile": leadership["reversal_5d_percentile"].get(sym),
            "sector_relative_return_5d": leadership["sector_relative_return_5d"].get(sym),
            "sector_relative_reversal_percentile": leadership["sector_relative_reversal_percentile"].get(sym),
        })

    percentiles = {k: _percentiles(rows, k) for k in COMPOSITE_WEIGHTS}
    for row in rows:
        avail = [(w, percentiles[k].get(row["symbol"])) for k, w in COMPOSITE_WEIGHTS.items()]
        usable = [(w, v) for w, v in avail if v is not None]
        row["score"] = (
            round(sum(w * v for w, v in usable) / sum(w for w, _ in usable), 1) if usable else None
        )
        row["technical_context_score"] = row["score"]
        rev = [v for v in (row["reversal_5d_percentile"], row["sector_relative_reversal_percentile"]) if v is not None]
        row["is_reversal_watch"] = bool(rev and max(rev) >= 90.0)

    data_gaps: list[str] = []
    if not sector_by_symbol:
        data_gaps.append(
            "No sector tags — sector_relative_return_5d / sector_relative_reversal_percentile "
            "are NULL. Needs the memberships scrape (Wikipedia S&P 500 GICS + SSGA sector-SPDR "
            "holdings); see docs/draft-design/09-…-audit.md §4.2."
        )
    if not have_spy:
        data_gaps.append("SPY history < 340 sessions — leadership overlay skipped.")

    return {
        "status": "descriptive_research",
        "universe": "assets.active = 1",
        "member_count": len(members),
        "eligible_count": len(rows),
        "latest_price_date": latest,
        "benchmark": "SPY (adjusted close)",
        "leadership_formation_count": leadership["formation_count"],
        "liquid_top100_count": len(leadership["liquidity_rank"]),
        "current_leader_count": len(leadership["current_leaders"]),
        "active_sleeve_count": sum(1 for v in leadership["candidate_weight"].values() if v > 0),
        "reversal_watch_count": sum(1 for r in rows if r["is_reversal_watch"]),
        "composite_weights": COMPOSITE_WEIGHTS,
        "data_gaps": data_gaps,
        "rows": rows,
        "sources": [
            {"role": "Universe", "table": "assets", "selection": "active = 1"},
            {"role": "Prices", "table": "price_bars", "selection": "adjusted close, raw close, volume"},
            {"role": "Benchmark", "table": "price_bars", "selection": "symbol = SPY"},
            {"role": "Sector tags", "table": "assets.sector",
             "selection": "derived by the memberships sync (11 sector SPDRs)"},
        ],
    }


# ---- caching (0008_ranking_runs.sql) ----------------------------------------

def _newest_price_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(last_date) AS d FROM price_bar_stats").fetchone()
    return row["d"] if row else None


def store_ranking(conn: sqlite3.Connection, result: dict[str, Any]) -> None:
    conn.execute("BEGIN")
    conn.execute(
        """
        INSERT INTO ranking_runs (latest_price_date, member_count, eligible_count,
                                  leadership_formation_count, payload_json)
        VALUES (?,?,?,?,?)
        """,
        (result.get("latest_price_date"), result.get("member_count"),
         result.get("eligible_count"), result.get("leadership_formation_count"),
         json.dumps(result)),
    )
    # keep the last 30 snapshots
    conn.execute(
        "DELETE FROM ranking_runs WHERE id NOT IN "
        "(SELECT id FROM ranking_runs ORDER BY id DESC LIMIT 30)"
    )
    conn.execute("COMMIT")


def latest_ranking(conn: sqlite3.Connection) -> dict[str, Any]:
    """The last stored snapshot + a staleness hint, or a 'not_computed' stub."""
    row = conn.execute(
        "SELECT computed_at, latest_price_date, payload_json FROM ranking_runs "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    newest = _newest_price_date(conn)
    if row is None:
        return {
            "status": "not_computed",
            "computed_at": None,
            "latest_price_date": None,
            "newest_price_date": newest,
            "stale": newest is not None,
            "rows": [],
        }
    payload = json.loads(row["payload_json"])
    payload["computed_at"] = row["computed_at"]
    payload["newest_price_date"] = newest
    payload["stale"] = bool(newest and row["latest_price_date"] and newest > row["latest_price_date"])
    return payload


def recompute_and_store(conn: sqlite3.Connection) -> dict[str, Any]:
    result = compute_ranking(conn)
    store_ranking(conn, result)
    result["computed_at"] = None  # set by latest_ranking on read; give the caller the fresh one
    return latest_ranking(conn)
