"""Equity/ETF daily bars.

Two Alpaca passes per batch — `adjustment=raw` (as-traded OHLCV) and
`adjustment=all` (the split/dividend-adjusted `adj_*` columns) — merged by
date. Neither pass is a "is it fresh?" probe; both carry real bar data, so
the handler avoids hitting the provider at all when it can:

* the bars come from the **`sip` consolidated feed** (config
  `alpaca_price_feed`): history back to 2016 with real market-wide volume,
  vs. the `iex` feed's ~mid-2020 start and ~3% of volume. The free plan will
  not serve SIP's most recent ~15 min, so SIP requests end at
  `today - alpaca_sip_end_lag_days` (the current session's bar lands on the
  next run).
* incremental mode skips any symbol whose `price_bar_stats.last_fetched` is
  already today's (UTC) calendar date — nothing new posts until the next
  session's close, so a re-run the same day is a no-op. `mode="full"`
  ignores this and re-pulls the whole history.
* symbols that do need data are grouped by their incremental start date and
  fetched in multi-symbol batches (one raw + one adjusted request per
  batch), not one pair of requests per symbol.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.features.data_management import runs
from app.providers.clients.alpaca_client import AlpacaClient

_UPSERT = """
INSERT INTO price_bars (
    symbol, date, open, high, low, close, volume,
    adj_open, adj_high, adj_low, adj_close, adj_volume,
    trade_count, vwap, feed, source, fetched_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'alpaca', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(symbol, date) DO UPDATE SET
    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
    volume=excluded.volume, adj_open=excluded.adj_open, adj_high=excluded.adj_high,
    adj_low=excluded.adj_low, adj_close=excluded.adj_close, adj_volume=excluded.adj_volume,
    trade_count=excluded.trade_count, vwap=excluded.vwap, feed=excluded.feed,
    fetched_at=excluded.fetched_at
"""


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _data_end(today: date) -> date:
    """Last date a request may ask for. SIP won't serve its most recent
    minutes on the free plan, so hold the end back a day; other feeds can go
    to today."""
    settings = get_settings()
    if settings.alpaca_price_feed == "sip":
        return today - timedelta(days=max(1, settings.alpaca_sip_end_lag_days))
    return today


def _batch_size(span_days: int) -> int:
    """Symbols per request. Keep each request's total bar count well under
    Alpaca's 10k-row page limit: an incremental tail is a handful of bars so
    a wide batch is safe; a long backfill needs a narrow one."""
    if span_days > 370:
        return 20
    if span_days > 90:
        return 50
    return 150


def _targets(conn: sqlite3.Connection, scope: str, scope_arg: str | None) -> list[str]:
    if scope == "single" and scope_arg:
        return [scope_arg.upper()]
    if scope == "watchlist":
        return [r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist ORDER BY symbol")]
    return [r["symbol"] for r in conn.execute("SELECT symbol FROM assets WHERE active = 1 ORDER BY symbol")]


def _plan(
    conn: sqlite3.Connection, targets: list[str], mode: str, today: date, data_end: date
) -> tuple[list[str], dict[str, list[str]]]:
    """Split targets into (skipped, {start_date: [symbols]}).

    Incremental mode skips a symbol that was already fetched today or is
    already current through `data_end`; everything else is grouped by the date
    its fetch should start from so same-start symbols batch into one request.
    """
    settings = get_settings()
    skipped: list[str] = []
    groups: dict[str, list[str]] = {}
    for symbol in targets:
        row = conn.execute(
            "SELECT last_date, last_fetched FROM price_bar_stats WHERE symbol = ?", (symbol,)
        ).fetchone()
        if mode != "full" and row and (row["last_fetched"] or "")[:10] == today.isoformat():
            skipped.append(symbol)  # already pulled today — nothing new until the next close
            continue
        if mode == "full" or not (row and row["last_date"]):
            start = settings.history_start_date
        else:
            start = (date.fromisoformat(row["last_date"]) + timedelta(days=1)).isoformat()
        if date.fromisoformat(start) > data_end:
            skipped.append(symbol)  # already current through the readable end
            continue
        groups.setdefault(start, []).append(symbol)
    return skipped, groups


def _merge(raw: list[dict], adj: list[dict], feed: str) -> list[tuple]:
    by_date: dict[str, dict] = {}
    for b in raw:
        d = b["t"][:10]
        by_date[d] = {
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "trade_count": b.get("n"), "vwap": b.get("vw"),
        }
    for b in adj:
        d = b["t"][:10]
        row = by_date.get(d)
        if row is None:
            continue
        row["adj_open"] = b["o"]; row["adj_high"] = b["h"]
        row["adj_low"] = b["l"]; row["adj_close"] = b["c"]; row["adj_volume"] = b["v"]

    out: list[tuple] = []
    for d, r in sorted(by_date.items()):
        out.append((
            d, r["open"], r["high"], r["low"], r["close"], r["volume"],
            r.get("adj_open"), r.get("adj_high"), r.get("adj_low"),
            r.get("adj_close"), r.get("adj_volume"), r.get("trade_count"), r.get("vwap"),
            feed,
        ))
    return out


def _write(conn: sqlite3.Connection, symbol: str, rows: list[tuple]) -> None:
    conn.execute("BEGIN")
    conn.executemany(_UPSERT, [(symbol, *r) for r in rows])
    stat = conn.execute(
        "SELECT COUNT(*) c, MIN(date) mn, MAX(date) mx FROM price_bars WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    last_close = conn.execute(
        "SELECT close FROM price_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,)
    ).fetchone()
    adv20 = conn.execute(
        "SELECT AVG(dv) FROM (SELECT close * volume dv FROM price_bars WHERE symbol = ? "
        "ORDER BY date DESC LIMIT 20)",
        (symbol,),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO price_bar_stats (symbol, bar_count, first_date, last_date, last_close,
                                     adv20_dollar, last_fetched)
        VALUES (?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT(symbol) DO UPDATE SET
            bar_count=excluded.bar_count, first_date=excluded.first_date,
            last_date=excluded.last_date, last_close=excluded.last_close,
            adv20_dollar=excluded.adv20_dollar, last_fetched=excluded.last_fetched
        """,
        (symbol, stat["c"], stat["mn"], stat["mx"],
         last_close["close"] if last_close else None,
         adv20[0] if adv20 else None),
    )
    conn.execute("COMMIT")


def _touch_fetched(conn: sqlite3.Connection, symbol: str) -> None:
    """Bump last_fetched for a symbol that was queried but had no new bars, so
    the 'already fetched today' skip covers it on the next incremental run.
    A no-op for a symbol with no stats row yet (no history at all)."""
    conn.execute(
        "UPDATE price_bar_stats SET last_fetched = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
        "WHERE symbol = ?",
        (symbol,),
    )


async def run_asset_prices(
    conn: sqlite3.Connection, run_id: int, mode: str, scope: str, scope_arg: str | None
) -> None:
    feed = get_settings().alpaca_price_feed
    targets = _targets(conn, scope, scope_arg)
    runs.set_planned(conn, run_id, len(targets))
    today = _today()
    data_end = _data_end(today)
    end = data_end.isoformat()

    skipped, groups = _plan(conn, targets, mode, today, data_end)
    for symbol in skipped:
        runs.raise_if_cancelled(run_id)
        runs.start_target(conn, run_id, symbol)
        runs.finish_target(conn, run_id, symbol, status="skipped", duration_ms=0)

    if not groups:
        return

    async with AlpacaClient() as client:
        for start, symbols in groups.items():
            size = _batch_size((data_end - date.fromisoformat(start)).days)
            for i in range(0, len(symbols), size):
                batch = symbols[i : i + size]
                runs.raise_if_cancelled(run_id)
                for symbol in batch:
                    runs.start_target(conn, run_id, symbol)
                label = batch[0] if len(batch) == 1 else f"{batch[0]} +{len(batch) - 1} more"
                conn.execute("UPDATE fetch_runs SET current_target = ? WHERE id = ?", (label, run_id))

                t0 = time.monotonic()
                try:
                    raw = await client.get_stock_bars(batch, start, end, "raw", feed=feed)
                    adj = await client.get_stock_bars(batch, start, end, "all", feed=feed)
                except Exception as exc:  # noqa: BLE001 - the whole batch failed
                    per = int((time.monotonic() - t0) * 1000 / len(batch))
                    for j, symbol in enumerate(batch):
                        runs.finish_target(conn, run_id, symbol, status="error",
                                           requests=2 if j == 0 else 0, duration_ms=per,
                                           error=str(exc)[:300])
                    continue

                per = int((time.monotonic() - t0) * 1000 / len(batch))
                for j, symbol in enumerate(batch):
                    rows = _merge(raw.get(symbol, []), adj.get(symbol, []), feed)
                    if rows:
                        _write(conn, symbol, rows)
                    else:
                        _touch_fetched(conn, symbol)
                    # 2 requests (raw + adjusted) cover the whole batch; charge
                    # them to its first symbol. Undercounts if a long backfill
                    # paginated, exact for incremental tails.
                    runs.finish_target(
                        conn, run_id, symbol, status="ok", rows=len(rows),
                        requests=2 if j == 0 else 0,
                        coverage_start=rows[0][0] if rows else None,
                        coverage_end=rows[-1][0] if rows else None,
                        duration_ms=per,
                    )
