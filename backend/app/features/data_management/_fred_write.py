"""Shared helpers for writing FRED observations into an (key, date, value) table.

macro_observations and commodity_prices have the same shape with different
column names — parametrize rather than duplicate.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from app.core.config import get_settings


def parse_value(raw: str | None) -> float | None:
    if raw is None or raw in (".", ""):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def start_date(last_date: str | None, mode: str) -> str:
    """First pull → history start; incremental → trailing-revision lookback."""
    settings = get_settings()
    if mode == "full" or not last_date:
        return settings.history_start_date
    back = date.fromisoformat(last_date) - timedelta(days=settings.fred_revision_lookback_days)
    return back.isoformat()


def upsert_observations(
    conn: sqlite3.Connection,
    *,
    table: str,
    key_col: str,
    key_val: str,
    value_col: str,
    observations: list[dict],
) -> int:
    sql = f"""
        INSERT INTO {table} ({key_col}, date, {value_col}, realtime_start, realtime_end, fetched_at)
        VALUES (?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT({key_col}, date) DO UPDATE SET
            {value_col}=excluded.{value_col},
            realtime_start=excluded.realtime_start,
            realtime_end=excluded.realtime_end,
            fetched_at=excluded.fetched_at
    """
    rows = [
        (key_val, o["date"], parse_value(o.get("value")),
         o.get("realtime_start"), o.get("realtime_end"))
        for o in observations
    ]
    conn.executemany(sql, rows)
    return len(rows)


def update_stats(
    conn: sqlite3.Connection,
    *,
    stats_table: str,
    key_col: str,
    key_val: str,
    src_table: str,
    src_value_col: str,
    count_col: str,
) -> None:
    stat = conn.execute(
        f"SELECT COUNT(*) c, MIN(date) mn, MAX(date) mx FROM {src_table} WHERE {key_col} = ?",
        (key_val,),
    ).fetchone()
    last_val = conn.execute(
        f"SELECT {src_value_col} v FROM {src_table} WHERE {key_col} = ? AND {src_value_col} IS NOT NULL "
        f"ORDER BY date DESC LIMIT 1",
        (key_val,),
    ).fetchone()
    conn.execute(
        f"""
        INSERT INTO {stats_table} ({key_col}, {count_col}, first_date, last_date, last_value, last_fetched)
        VALUES (?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT({key_col}) DO UPDATE SET
            {count_col}=excluded.{count_col}, first_date=excluded.first_date,
            last_date=excluded.last_date, last_value=excluded.last_value,
            last_fetched=excluded.last_fetched
        """,
        (key_val, stat["c"], stat["mn"], stat["mx"], last_val["v"] if last_val else None),
    )
