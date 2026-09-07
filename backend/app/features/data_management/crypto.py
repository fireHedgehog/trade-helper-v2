"""BTC/USD and ETH/USD daily trade candles from Coinbase Exchange.

Requests end at **yesterday (UTC)**: the current UTC day's bar is still
forming, and storing that partial bar would feed a half-day close into the
signal engine / 60-day vol. The `(symbol, date)` upsert keeps every re-fetch
idempotent. Incremental fetches overlap the last stored day. A different stored
source triggers a complete, validated replacement before incremental updates.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.features.data_management import runs
from app.providers.clients.coinbase_client import CoinbaseClient

_UPSERT = """
INSERT INTO crypto_bars (symbol, date, open, high, low, close, volume, trade_count, vwap,
                         source, fetched_at)
VALUES (?,?,?,?,?,?,?,?,?, 'coinbase', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(symbol, date) DO UPDATE SET
    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
    volume=excluded.volume, trade_count=excluded.trade_count, vwap=excluded.vwap,
    source=excluded.source, fetched_at=excluded.fetched_at
"""


def _end_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def _validate_coverage(bars: list[dict], required_start: str | None, end: str) -> None:
    if not bars:
        raise ValueError("Coinbase returned no completed daily candles; stored history retained")
    first, last = bars[0]["t"][:10], bars[-1]["t"][:10]
    if required_start and first > required_start:
        raise ValueError(f"Coinbase history starts at {first}, missing {required_start}; stored history retained")
    if last != end:
        raise ValueError(f"Coinbase history ends at {last}, expected {end}; stored history retained")
    expected = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1
    if len(bars) != expected:
        raise ValueError("Coinbase daily history has missing dates; stored history retained")


def _write(conn: sqlite3.Connection, symbol: str, bars: list[dict], *, replace: bool = False) -> int:
    rows = [
        (symbol, b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"], b.get("n"), b.get("vw"))
        for b in bars
    ]
    conn.execute("BEGIN")
    try:
        if replace:
            conn.execute("DELETE FROM crypto_bars WHERE symbol = ?", (symbol,))
        conn.executemany(_UPSERT, rows)
        _update_stats(conn, symbol)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def _update_stats(conn: sqlite3.Connection, symbol: str) -> None:
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


async def run_crypto_bars(conn: sqlite3.Connection, run_id: int, mode: str) -> None:
    targets = [
        r["symbol"] for r in conn.execute(
            "SELECT symbol FROM crypto_assets WHERE active = 1 ORDER BY symbol"
        )
    ] or ["BTC/USD", "ETH/USD"]
    runs.set_planned(conn, run_id, len(targets))
    # End at yesterday (UTC) — the current day's bar is still forming.
    end = _end_date()

    async with CoinbaseClient() as client:
        for symbol in targets:
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, symbol)
            t0 = time.monotonic()
            requests_before = client.requests_made
            try:
                stored = conn.execute(
                    "SELECT MIN(date) first_date, MAX(date) last_date, "
                    "SUM(CASE WHEN source IS NOT 'coinbase' THEN 1 ELSE 0 END) other_source "
                    "FROM crypto_bars WHERE symbol = ?", (symbol,),
                ).fetchone()
                source_changed = bool(stored["other_source"])
                replace = mode == "full" or source_changed
                if replace or not stored["last_date"]:
                    start = min(get_settings().crypto_history_start_date,
                                stored["first_date"] or get_settings().crypto_history_start_date)
                    required_start = stored["first_date"]
                else:
                    # Recheck the last completed candle, including a same-day rerun.
                    start = min(stored["last_date"], end)
                    required_start = start
                bars = await client.get_crypto_bars(
                    symbol, start, end, check_cancel=lambda: runs.raise_if_cancelled(run_id),
                )
                runs.raise_if_cancelled(run_id)
                _validate_coverage(bars, required_start, end)
                n = _write(conn, symbol, bars, replace=replace)
                runs.finish_target(
                    conn, run_id, symbol, status="ok", rows=n,
                    requests=client.requests_made - requests_before,
                    coverage_start=bars[0]["t"][:10],
                    coverage_end=bars[-1]["t"][:10],
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    note="Source changed to Coinbase; full history replaced" if source_changed else None,
                )
            except runs.RunCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                runs.finish_target(conn, run_id, symbol, status="error",
                                   requests=client.requests_made - requests_before,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])
