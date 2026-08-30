"""Asset-catalog sync: Alpaca /v2/assets (equity active + inactive, crypto).

Upserts `assets` / `crypto_assets` (metadata only), then recomputes the
`active` price-fetch set (`universe.recompute_active_universe` = the hand seed
∪ current index / core-ETF memberships).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time

from app.features.data_management import runs
from app.features.data_management.universe import recompute_active_universe
from app.providers.clients.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


def _bool(v: object) -> int:
    return 1 if v else 0


async def run_asset_catalog(conn: sqlite3.Connection, run_id: int) -> None:
    runs.set_planned(conn, run_id, 3)

    async with AlpacaClient() as client:
        for target, status, asset_class in (
            ("equity:active", "active", "us_equity"),
            ("equity:inactive", "inactive", "us_equity"),
            ("crypto:active", "active", "crypto"),
        ):
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, target)
            t0 = time.monotonic()
            try:
                assets = await client.list_assets(status, asset_class)
                if asset_class == "crypto":
                    rows = _upsert_crypto(conn, assets)
                else:
                    rows = _upsert_equities(conn, assets, status)
                runs.finish_target(
                    conn, run_id, target,
                    status="ok", rows=rows, requests=1,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - one bad target must not abort the run
                runs.finish_target(
                    conn, run_id, target, status="error", requests=1,
                    duration_ms=int((time.monotonic() - t0) * 1000), error=str(exc)[:300],
                )

    recompute_active_universe(conn)


def _upsert_equities(conn: sqlite3.Connection, assets: list[dict], status: str) -> int:
    conn.execute("BEGIN")
    n = 0
    for a in assets:
        attrs = a.get("attributes") or []
        conn.execute(
            """
            INSERT INTO assets (
                symbol, alpaca_asset_id, name, asset_class, exchange, status,
                tradable, marginable, shortable, fractionable, borrow_status,
                margin_requirement_long, margin_requirement_short, cusip,
                has_options, attributes_json, last_synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(symbol) DO UPDATE SET
                alpaca_asset_id=excluded.alpaca_asset_id, name=excluded.name,
                asset_class=excluded.asset_class, exchange=excluded.exchange,
                status=excluded.status, tradable=excluded.tradable,
                marginable=excluded.marginable, shortable=excluded.shortable,
                fractionable=excluded.fractionable, borrow_status=excluded.borrow_status,
                margin_requirement_long=excluded.margin_requirement_long,
                margin_requirement_short=excluded.margin_requirement_short,
                cusip=excluded.cusip, has_options=excluded.has_options,
                attributes_json=excluded.attributes_json,
                last_synced_at=excluded.last_synced_at
            """,
            (
                a.get("symbol"), a.get("id"), a.get("name"), a.get("class", "us_equity"),
                a.get("exchange"), a.get("status", status),
                _bool(a.get("tradable")), _bool(a.get("marginable")),
                _bool(a.get("shortable")), _bool(a.get("fractionable")),
                a.get("borrow_status"),
                a.get("margin_requirement_long"), a.get("margin_requirement_short"),
                a.get("cusip"), _bool("has_options" in attrs), json.dumps(attrs),
            ),
        )
        n += 1
    conn.execute("COMMIT")
    return n


def _upsert_crypto(conn: sqlite3.Connection, assets: list[dict]) -> int:
    conn.execute("BEGIN")
    n = 0
    for a in assets:
        conn.execute(
            """
            INSERT INTO crypto_assets (
                symbol, alpaca_asset_id, name, status, tradable,
                min_order_size, min_trade_increment, price_increment, last_synced_at
            ) VALUES (?,?,?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(symbol) DO UPDATE SET
                alpaca_asset_id=excluded.alpaca_asset_id, name=excluded.name,
                status=excluded.status, tradable=excluded.tradable,
                min_order_size=excluded.min_order_size,
                min_trade_increment=excluded.min_trade_increment,
                price_increment=excluded.price_increment,
                last_synced_at=excluded.last_synced_at
            """,
            (
                a.get("symbol"), a.get("id"), a.get("name"), a.get("status", "active"),
                _bool(a.get("tradable")), a.get("min_order_size"),
                a.get("min_trade_increment"), a.get("price_increment"),
            ),
        )
        n += 1
    conn.execute("COMMIT")
    return n
