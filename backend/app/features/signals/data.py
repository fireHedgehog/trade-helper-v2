"""OHLC loader for the signal engine.

Equities/ETFs use the split/dividend-adjusted series from `price_bars`
(docs/draft-design/04-trend-page.md — returns need the adjusted basis, and the
chart shows the same basis the rule ran on). Crypto (`*/USD`) uses the raw
`crypto_bars` — no corporate actions there.
"""

from __future__ import annotations

import sqlite3


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    # accept BTC-USD / BTCUSD from a URL path for the crypto pairs
    if s in {"BTC-USD", "BTCUSD"}:
        return "BTC/USD"
    if s in {"ETH-USD", "ETHUSD"}:
        return "ETH/USD"
    return s


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def load_ohlc(conn: sqlite3.Connection, symbol: str) -> list[dict]:
    symbol = normalize_symbol(symbol)
    if is_crypto(symbol):
        rows = conn.execute(
            "SELECT date, open AS o, high AS h, low AS l, close AS c, volume AS v "
            "FROM crypto_bars WHERE symbol = ? ORDER BY date",
            (symbol,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, adj_open AS o, adj_high AS h, adj_low AS l, adj_close AS c, "
            "volume AS v FROM price_bars "
            "WHERE symbol = ? AND adj_close IS NOT NULL ORDER BY date",
            (symbol,),
        ).fetchall()
    bars = [dict(r) for r in rows]
    return [b for b in bars if b["c"] and b["c"] > 0 and b["o"] and b["h"] and b["l"]]


def latest_price_date(conn: sqlite3.Connection, symbol: str) -> str | None:
    symbol = normalize_symbol(symbol)
    table, stat = ("crypto_bar_stats", "crypto") if is_crypto(symbol) else ("price_bar_stats", "eq")
    row = conn.execute(
        f"SELECT last_date FROM {table} WHERE symbol = ?", (symbol,)
    ).fetchone()
    return row["last_date"] if row and row["last_date"] else None
