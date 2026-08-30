"""Read queries for the Data Management browse tables.

Server-side pagination everywhere, page size hard-capped. List views join the
maintained *_stats tables so they never scan the big fact tables. (Keyset
pagination for the fact tables is a later optimization; at Phase-1 universe
size offset pagination on an indexed table is fine.)
"""

from __future__ import annotations

import sqlite3

MAX_PAGE_SIZE = 200


def _clamp_page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size, (page - 1) * page_size


# ---- assets ----

def list_assets(
    conn: sqlite3.Connection,
    q: str | None,
    page: int,
    page_size: int,
    active_only: bool,
) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    where = []
    params: list = []
    if active_only:
        where.append("a.active = 1")
    if q:
        where.append("(a.symbol LIKE ? OR a.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = conn.execute(f"SELECT COUNT(*) FROM assets a {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT a.symbol, a.name, a.asset_class, a.exchange, a.sector, a.status,
               a.has_options, a.active,
               s.bar_count, s.first_date, s.last_date, s.last_close, s.last_fetched,
               (SELECT GROUP_CONCAT(group_key) FROM symbol_memberships m
                 WHERE m.symbol = a.symbol AND m.active = 1) AS memberships
          FROM assets a
          LEFT JOIN price_bar_stats s ON s.symbol = a.symbol
          {clause}
      ORDER BY a.active DESC, a.symbol
         LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def get_asset(conn: sqlite3.Connection, symbol: str) -> dict | None:
    a = conn.execute("SELECT * FROM assets WHERE symbol = ?", (symbol,)).fetchone()
    if not a:
        return None
    stats = conn.execute("SELECT * FROM price_bar_stats WHERE symbol = ?", (symbol,)).fetchone()
    memberships = conn.execute(
        """
        SELECT m.group_key, g.name, g.group_type, m.weight, m.active
          FROM symbol_memberships m
          LEFT JOIN membership_groups g ON g.group_key = m.group_key
         WHERE m.symbol = ?
      ORDER BY g.group_type, m.group_key
        """,
        (symbol,),
    ).fetchall()
    return {
        "asset": dict(a),
        "stats": dict(stats) if stats else None,
        "memberships": [dict(m) for m in memberships],
    }


def list_price_bars(conn: sqlite3.Connection, symbol: str, page: int, page_size: int) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    total = conn.execute(
        "SELECT COUNT(*) FROM price_bars WHERE symbol = ?", (symbol,)
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT date, open, high, low, close, volume,
               adj_open, adj_high, adj_low, adj_close, adj_volume,
               trade_count, vwap, feed, fetched_at
          FROM price_bars WHERE symbol = ?
      ORDER BY date DESC LIMIT ? OFFSET ?
        """,
        (symbol, page_size, offset),
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


# ---- macro ----

def list_macro(conn: sqlite3.Connection, category: str | None) -> list[dict]:
    clause, params = ("WHERE c.category = ?", [category]) if category else ("", [])
    rows = conn.execute(
        f"""
        SELECT c.series_id, c.title, c.short_label, c.category, c.frequency, c.units_short,
               c.tracked, c.typical_lag_days, c.observation_end, c.last_fetched_at,
               s.point_count, s.first_date, s.last_date, s.last_value, s.last_fetched
          FROM macro_series_catalog c
          LEFT JOIN macro_obs_stats s ON s.series_id = c.series_id
          {clause}
      ORDER BY c.category, c.series_id
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def list_macro_observations(
    conn: sqlite3.Connection, series_id: str, page: int, page_size: int
) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    total = conn.execute(
        "SELECT COUNT(*) FROM macro_observations WHERE series_id = ?", (series_id,)
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT date, value, realtime_start, realtime_end, fetched_at
          FROM macro_observations WHERE series_id = ?
      ORDER BY date DESC LIMIT ? OFFSET ?
        """,
        (series_id, page_size, offset),
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def macro_recent(conn: sqlite3.Connection, series_id: str, n: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT date, value FROM macro_observations WHERE series_id = ? AND value IS NOT NULL "
        "ORDER BY date DESC LIMIT ?",
        (series_id, n),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---- crypto ----

def list_crypto(conn: sqlite3.Connection) -> list[dict]:
    # Only the pairs we actually track (active) or have already fetched — the
    # Alpaca crypto catalog has ~70 pairs and dumping them all is noise.
    rows = conn.execute(
        """
        SELECT a.symbol, a.name, a.status, a.active,
               s.bar_count, s.first_date, s.last_date, s.last_close, s.last_fetched
          FROM crypto_assets a
          LEFT JOIN crypto_bar_stats s ON s.symbol = a.symbol
         WHERE a.active = 1 OR COALESCE(s.bar_count, 0) > 0
      ORDER BY a.active DESC, a.symbol
        """
    ).fetchall()
    return [dict(r) for r in rows]


def list_crypto_bars(conn: sqlite3.Connection, symbol: str, page: int, page_size: int) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    total = conn.execute(
        "SELECT COUNT(*) FROM crypto_bars WHERE symbol = ?", (symbol,)
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT date, open, high, low, close, volume, trade_count, vwap, fetched_at
          FROM crypto_bars WHERE symbol = ?
      ORDER BY date DESC LIMIT ? OFFSET ?
        """,
        (symbol, page_size, offset),
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


# ---- commodities ----

def list_memberships(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT g.group_key, g.group_type, g.name, g.gics_sector, g.source_url,
                   g.last_source_as_of, g.last_synced_at,
                   (SELECT COUNT(*) FROM symbol_memberships m
                     WHERE m.group_key = g.group_key AND m.active = 1) AS member_count,
                   (SELECT COUNT(*) FROM symbol_memberships m
                     JOIN assets a ON a.symbol = m.symbol
                    WHERE m.group_key = g.group_key AND m.active = 1) AS in_universe_count
              FROM membership_groups g
          ORDER BY g.group_type, g.group_key
            """
        )
    ]


def list_group_members(conn: sqlite3.Connection, group_key: str, page: int, page_size: int) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    total = conn.execute(
        "SELECT COUNT(*) FROM symbol_memberships WHERE group_key = ? AND active = 1", (group_key,)
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT m.symbol, a.name, a.sector, m.weight, m.source, m.source_as_of,
               (a.symbol IS NOT NULL) AS in_universe
          FROM symbol_memberships m
          LEFT JOIN assets a ON a.symbol = m.symbol
         WHERE m.group_key = ? AND m.active = 1
      ORDER BY m.weight DESC NULLS LAST, m.symbol
         LIMIT ? OFFSET ?
        """,
        (group_key, page_size, offset),
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def list_option_stats(conn: sqlite3.Connection) -> list[dict]:
    """Per-underlying option-snapshot coverage (research set + what's stored)."""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT r.underlying, r.bucket,
                   s.last_snapshot, s.snapshot_rows, s.last_fetched,
                   (SELECT COUNT(DISTINCT snapshot_date) FROM option_chain_snapshots o
                     WHERE o.underlying = r.underlying) AS snapshot_days,
                   (SELECT COUNT(*) FROM option_chain_snapshots o
                     WHERE o.underlying = r.underlying
                       AND o.snapshot_date = s.last_snapshot) AS last_day_rows
              FROM options_research_set r
              LEFT JOIN option_snapshot_stats s ON s.underlying = r.underlying
          ORDER BY r.bucket, r.underlying
            """
        )
    ]


def list_commodities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.instrument, c.name, c.fred_series_id, c.unit, c.category,
               c.observation_end, c.last_fetched_at,
               s.point_count, s.first_date, s.last_date, s.last_value, s.last_fetched
          FROM commodity_series c
          LEFT JOIN commodity_price_stats s ON s.instrument = c.instrument
      ORDER BY c.category, c.instrument
        """
    ).fetchall()
    return [dict(r) for r in rows]


def list_commodity_prices(
    conn: sqlite3.Connection, instrument: str, page: int, page_size: int
) -> dict:
    page, page_size, offset = _clamp_page(page, page_size)
    total = conn.execute(
        "SELECT COUNT(*) FROM commodity_prices WHERE instrument = ?", (instrument,)
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT date, price, realtime_start, realtime_end, fetched_at
          FROM commodity_prices WHERE instrument = ?
      ORDER BY date DESC LIMIT ? OFFSET ?
        """,
        (instrument, page_size, offset),
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}
