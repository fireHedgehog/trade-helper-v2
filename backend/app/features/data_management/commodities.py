"""Commodity reference prices (FRED daily): WTI, Brent, Gold, NatGas.

Same FRED endpoints/pacing as macro, but its own family table
(commodity_prices) — a tradable price, not an economic indicator.
"""

from __future__ import annotations

import sqlite3
import time

from app.features.data_management import runs
from app.features.data_management._fred_write import start_date, update_stats, upsert_observations
from app.providers.clients.fred_client import FredClient


async def run_commodities(conn: sqlite3.Connection, run_id: int, mode: str) -> None:
    targets = conn.execute(
        "SELECT instrument, fred_series_id FROM commodity_series ORDER BY instrument"
    ).fetchall()
    runs.set_planned(conn, run_id, len(targets))

    async with FredClient() as client:
        for row in targets:
            instrument, series_id = row["instrument"], row["fred_series_id"]
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, instrument)
            t0 = time.monotonic()
            try:
                last = conn.execute(
                    "SELECT last_date FROM commodity_price_stats WHERE instrument = ?", (instrument,)
                ).fetchone()
                start = start_date(last["last_date"] if last else None, mode)

                meta = await client.get_series(series_id)
                obs = await client.get_observations(series_id, start)

                conn.execute("BEGIN")
                if meta:
                    conn.execute(
                        """
                        UPDATE commodity_series SET
                            observation_start=?, observation_end=?, fred_last_updated=?,
                            last_fetched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                        WHERE instrument=?
                        """,
                        (meta.get("observation_start"), meta.get("observation_end"),
                         meta.get("last_updated"), instrument),
                    )
                n = upsert_observations(
                    conn, table="commodity_prices", key_col="instrument",
                    key_val=instrument, value_col="price", observations=obs,
                )
                update_stats(
                    conn, stats_table="commodity_price_stats", key_col="instrument",
                    key_val=instrument, src_table="commodity_prices", src_value_col="price",
                    count_col="point_count",
                )
                conn.execute("COMMIT")

                runs.finish_target(
                    conn, run_id, instrument, status="ok", rows=n, requests=2,
                    coverage_start=obs[0]["date"] if obs else None,
                    coverage_end=obs[-1]["date"] if obs else None,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                runs.finish_target(conn, run_id, instrument, status="error", requests=2,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])
