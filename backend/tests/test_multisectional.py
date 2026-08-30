"""Cross-sectional ranking — shape + a smoke computation over seeded bars."""

from __future__ import annotations

import math
from datetime import date, timedelta


def _seed(conn, symbols_with_drift: dict[str, float], days: int = 400) -> None:
    """Give each symbol `days` business-day adjusted-close bars that drift by
    `drift` per day off a base of 100, with a raw close ≈ adj and volume."""
    start = date(2025, 1, 1)
    conn.execute("BEGIN")
    for sym, drift in symbols_with_drift.items():
        conn.execute(
            "INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
            "VALUES (?,?,?,?,1)",
            (sym, f"{sym} Inc", "us_equity", "active"),
        )
        d = start
        n = 0
        rows = []
        while n < days:
            if d.weekday() < 5:
                px = 100.0 * math.exp(drift * n)
                rows.append((sym, d.isoformat(), px, px, px, px, 1_000_000, px, px, px, px, 1_000_000))
                n += 1
            d += timedelta(days=1)
        conn.executemany(
            "INSERT OR REPLACE INTO price_bars "
            "(symbol, date, open, high, low, close, volume, adj_open, adj_high, adj_low, adj_close, adj_volume) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    conn.execute("COMMIT")


def test_ranking_not_computed_by_default(client):
    body = client.get("/api/multisectional/ranking").json()
    assert body["status"] == "not_computed"
    assert body["rows"] == []
    assert body["computed_at"] is None


def test_recompute_stores_a_snapshot_and_get_reads_it(client):
    from app.db.connection import get_connection

    with get_connection() as conn:
        _seed(conn, {"SPY": 0.0003, "AAA": 0.0009})

    fresh = client.post("/api/multisectional/ranking/recompute").json()
    assert fresh["status"] == "descriptive_research"
    assert fresh["computed_at"]
    assert fresh["stale"] is False

    cached = client.get("/api/multisectional/ranking").json()
    assert cached["computed_at"] == fresh["computed_at"]
    assert cached["member_count"] == fresh["member_count"]


def test_ranking_computes_over_seeded_bars(client):
    from app.db.connection import get_connection

    with get_connection() as conn:
        _seed(conn, {"SPY": 0.0003, "AAA": 0.0009, "BBB": 0.0006, "CCC": -0.0004, "DDD": 0.0001})

    body = client.post("/api/multisectional/ranking/recompute").json()
    assert body["member_count"] == 5
    assert body["eligible_count"] >= 4  # SPY is a member too
    by = {r["symbol"]: r for r in body["rows"]}

    # AAA drifts up fastest → strongest 3m excess vs SPY, best structure.
    assert by["AAA"]["rs_3m"] > by["BBB"]["rs_3m"] > by["CCC"]["rs_3m"]
    assert by["AAA"]["above_all_mas"] is True
    assert by["AAA"]["ordered_mas"] is True
    assert by["CCC"]["above_all_mas"] is False

    # composite score is a 0-100 percentile blend
    for r in body["rows"]:
        assert r["score"] is None or 0 <= r["score"] <= 100

    # leadership overlay ran (400 bars > 340)
    assert body["leadership_formation_count"] == 13
    assert body["liquid_top100_count"] >= 4
    assert by["AAA"]["leadership_persistence"] is not None
    # AAA should be a persistent leader; CCC should not
    assert by["AAA"]["leadership_persistence"] >= by["CCC"]["leadership_persistence"]


def test_ranking_screens_and_sorts_are_stable(client):
    """The frontend screen/sort keys must all exist on every row."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        _seed(conn, {"SPY": 0.0002, "AAA": 0.0007, "BBB": -0.0003})

    rows = client.post("/api/multisectional/ranking/recompute").json()["rows"]
    keys = {
        "leadership_persistence", "rs_3m_percentile", "candidate_weight", "liquidity_rank",
        "score", "rs_3m", "rs_6m", "rs_12m", "high_52w_distance", "trend_distance", "slope",
        "median_dollar_volume_21d", "is_liquid_top100", "is_current_leader", "above_all_mas",
        "ordered_mas", "is_reversal_watch", "return_5d", "reversal_5d_percentile",
        "sector_relative_return_5d", "sector_relative_reversal_percentile",
    }
    for r in rows:
        assert keys <= set(r)
