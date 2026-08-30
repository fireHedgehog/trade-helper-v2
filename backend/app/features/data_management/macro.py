"""Macro series fetch (FRED): metadata → catalog, observations → macro_observations."""

from __future__ import annotations

import sqlite3
import time

from app.features.data_management import runs
from app.features.data_management._fred_write import start_date, update_stats, upsert_observations
from app.providers.clients.fred_client import FredClient


def _update_catalog(conn: sqlite3.Connection, series_id: str, meta: dict) -> None:
    conn.execute(
        """
        UPDATE macro_series_catalog SET
            title=?, units=?, units_short=?, frequency=?, seasonal_adjustment=?,
            observation_start=?, observation_end=?, fred_last_updated=?, popularity=?,
            notes=?, last_fetched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE series_id=?
        """,
        (
            meta.get("title"), meta.get("units"), meta.get("units_short"),
            meta.get("frequency"), meta.get("seasonal_adjustment"),
            meta.get("observation_start"), meta.get("observation_end"),
            meta.get("last_updated"), meta.get("popularity"),
            (meta.get("notes") or "")[:2000], series_id,
        ),
    )


async def run_macro(conn: sqlite3.Connection, run_id: int, mode: str) -> None:
    targets = [
        r["series_id"] for r in conn.execute(
            "SELECT series_id FROM macro_series_catalog WHERE tracked = 1 ORDER BY category, series_id"
        )
    ]
    runs.set_planned(conn, run_id, len(targets))

    async with FredClient() as client:
        for series_id in targets:
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, series_id)
            t0 = time.monotonic()
            try:
                last = conn.execute(
                    "SELECT last_date FROM macro_obs_stats WHERE series_id = ?", (series_id,)
                ).fetchone()
                start = start_date(last["last_date"] if last else None, mode)

                meta = await client.get_series(series_id)
                obs = await client.get_observations(series_id, start)

                conn.execute("BEGIN")
                if meta:
                    _update_catalog(conn, series_id, meta)
                n = upsert_observations(
                    conn, table="macro_observations", key_col="series_id",
                    key_val=series_id, value_col="value", observations=obs,
                )
                update_stats(
                    conn, stats_table="macro_obs_stats", key_col="series_id", key_val=series_id,
                    src_table="macro_observations", src_value_col="value", count_col="point_count",
                )
                conn.execute("COMMIT")

                runs.finish_target(
                    conn, run_id, series_id, status="ok", rows=n, requests=2,
                    coverage_start=obs[0]["date"] if obs else None,
                    coverage_end=obs[-1]["date"] if obs else None,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                runs.finish_target(conn, run_id, series_id, status="error", requests=2,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])
