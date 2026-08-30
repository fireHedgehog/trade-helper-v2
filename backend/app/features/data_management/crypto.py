"""Crypto daily bars (BTC/USD, ETH/USD) — one Alpaca pass, no adjustment."""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.features.data_management import runs
from app.providers.clients.alpaca_client import AlpacaClient

_UPSERT = """
INSERT INTO crypto_bars (symbol, date, open, high, low, close, volume, trade_count, vwap,
                         source, fetched_at)
VALUES (?,?,?,?,?,?,?,?,?, 'alpaca', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(symbol, date) DO UPDATE SET
    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
    volume=excluded.volume, trade_count=excluded.trade_count, vwap=excluded.vwap,
    fetched_at=excluded.fetched_at
"""


def _start_for(conn: sqlite3.Connection, symbol: str, mode: str) -> str:
    settings = get_settings()
    if mode == "full":
        return settings.history_start_date
    row = conn.execute(
        "SELECT last_date FROM crypto_bar_stats WHERE symbol = ?", (symbol,)
    ).fetchone()
    if row and row["last_date"]:
        return (date.fromisoformat(row["last_date"]) + timedelta(days=1)).isoformat()
    return settings.history_start_date


def _write(conn: sqlite3.Connection, symbol: str, bars: list[dict]) -> int:
    rows = [
        (symbol, b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"], b.get("n"), b.get("vw"))
        for b in bars
    ]
    conn.execute("BEGIN")
    conn.executemany(_UPSERT, rows)
    stat = conn.execute(
        "SELECT COUNT(*) c, MIN(date) mn, MAX(date) mx FROM crypto_bars WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    last_close = conn.execute(
        "SELECT close FROM crypto_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,)
    ).fetchone()
    conn.execute(
        """
        INSERT INTO crypto_bar_stats (symbol, bar_count, first_date, last_date, last_close,
                                      last_fetched)
        VALUES (?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT(symbol) DO UPDATE SET
            bar_count=excluded.bar_count, first_date=excluded.first_date,
            last_date=excluded.last_date, last_close=excluded.last_close,
            last_fetched=excluded.last_fetched
        """,
        (symbol, stat["c"], stat["mn"], stat["mx"], last_close["close"] if last_close else None),
    )
    conn.execute("COMMIT")
    return len(rows)


async def run_crypto_bars(conn: sqlite3.Connection, run_id: int, mode: str) -> None:
    targets = [
        r["symbol"] for r in conn.execute(
            "SELECT symbol FROM crypto_assets WHERE active = 1 ORDER BY symbol"
        )
    ] or ["BTC/USD", "ETH/USD"]
    runs.set_planned(conn, run_id, len(targets))
    today = datetime.now(timezone.utc).date().isoformat()

    async with AlpacaClient() as client:
        for symbol in targets:
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, symbol)
            t0 = time.monotonic()
            try:
                start = _start_for(conn, symbol, mode)
                bars = (await client.get_crypto_bars([symbol], start, today)).get(symbol, [])
                n = _write(conn, symbol, bars) if bars else 0
                runs.finish_target(
                    conn, run_id, symbol, status="ok", rows=n, requests=1,
                    coverage_start=bars[0]["t"][:10] if bars else None,
                    coverage_end=bars[-1]["t"][:10] if bars else None,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                runs.finish_target(conn, run_id, symbol, status="error", requests=1,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])
