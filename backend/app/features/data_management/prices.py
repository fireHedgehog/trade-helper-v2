"""Equity/ETF daily bars.

Two Alpaca passes per batch — `adjustment=raw` (as-traded OHLCV) and
`adjustment=all` (the split/dividend-adjusted `adj_*` columns) — merged by
date. Neither pass is a "is it fresh?" probe; both carry real bar data, so
the handler avoids hitting the provider at all when it can:

* the bars come from the **`sip` consolidated feed** (config
  `alpaca_price_feed`): history back to 2016 with real market-wide volume,
  vs. the `iex` feed's ~mid-2020 start and ~3% of volume. The free plan
  refuses SIP data for the current **America/New_York** day (`403`), so
  requests end at "yesterday in ET", rolled back over weekends — computed in
  ET, NOT the server's UTC date, so a run from a UTC+12/13 timezone doesn't
  trail the real US date by a day (`_data_end`).
* incremental mode skips a symbol that is already current through that end,
  or that was hit within `_RETRY_COOLDOWN` (6 h) and found nothing new — so a
  weekend / holiday re-run doesn't spam the provider, but a re-run after the
  next session clears the embargo does pick the new bar up. `mode="full"`
  ignores both and re-pulls the whole history. The `(symbol, date)` upsert
  makes any repeat fetch idempotent — a day is never appended twice.
* symbols that do need data are grouped by their incremental start date and
  fetched in multi-symbol batches (one raw + one adjusted request per
  batch), not one pair of requests per symbol.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.features.data_management import runs
from app.providers.clients.alpaca_client import AlpacaClient
from app.providers.clients.http import FetchHTTPError

_ET = ZoneInfo("America/New_York")
# After a run that found nothing new for a symbol, don't re-hit the provider
# for it again within this window — suppresses weekend / holiday spam without
# blocking a pickup once a new session's bar clears the SIP embargo.
_RETRY_COOLDOWN = timedelta(hours=6)
# The free Alpaca plan refuses SIP data that is "too recent" with a 403; the
# exact cut-over (ET midnight vs the next session's close) is fuzzy, so on that
# error we retreat the request end one day at a time and, if it never clears,
# mark the symbols skipped rather than failed.
_SIP_EMBARGO_MARKER = "recent sip data"
_SIP_EMBARGO_MAX_RETREAT = 3

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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _data_end(now_utc: datetime) -> date:
    """Last date a request may ask for.

    Computed in **America/New_York**, not the server's UTC calendar date — a
    run from a UTC+12/13 timezone would otherwise trail the real US date by a
    day. On the `sip` feed the free Alpaca plan refuses the **current ET day**
    entirely (`403 "subscription does not permit querying recent SIP data"`),
    so the newest servable bar is the previous trading day; that session's bar
    lands on the first run after ET midnight. `alpaca_sip_end_lag_days` holds
    it back further. Other feeds have no embargo and can go to today.

    Holidays are not special-cased: a request that spans one just returns no
    bars, the upsert is a no-op, and `last_date` never advances past the true
    last session.
    """
    settings = get_settings()
    today_et = now_utc.astimezone(_ET).date()
    if settings.alpaca_price_feed != "sip":
        return today_et
    d = today_et - timedelta(days=1)  # SIP free plan embargoes the current ET day
    for _ in range(max(0, settings.alpaca_sip_end_lag_days)):
        d -= timedelta(days=1)
    while d.weekday() >= 5:  # roll Sat=5 / Sun=6 back to a weekday
        d -= timedelta(days=1)
    return d


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


def _fetched_within_cooldown(last_fetched: str | None, now_utc: datetime) -> bool:
    if not last_fetched:
        return False
    try:
        lf = datetime.fromisoformat(last_fetched.replace("Z", "+00:00"))
    except ValueError:
        return False
    if lf.tzinfo is None:
        lf = lf.replace(tzinfo=timezone.utc)
    return now_utc - lf < _RETRY_COOLDOWN


def _plan(
    conn: sqlite3.Connection, targets: list[str], mode: str, now_utc: datetime, data_end: date
) -> tuple[list[str], dict[str, list[str]]]:
    """Split targets into (skipped, {start_date: [symbols]}).

    Incremental mode skips a symbol that is already current through `data_end`,
    or that we hit within `_RETRY_COOLDOWN` and found nothing new for (weekend /
    holiday spam guard); everything else is grouped by the date its fetch should
    start from so same-start symbols batch into one request.
    """
    settings = get_settings()
    skipped: list[str] = []
    groups: dict[str, list[str]] = {}
    for symbol in targets:
        row = conn.execute(
            "SELECT last_date, last_fetched FROM price_bar_stats WHERE symbol = ?", (symbol,)
        ).fetchone()
        if mode == "full" or not (row and row["last_date"]):
            start = settings.history_start_date
        else:
            start = (date.fromisoformat(row["last_date"]) + timedelta(days=1)).isoformat()
        if date.fromisoformat(start) > data_end:
            skipped.append(symbol)  # already current through the readable end
            continue
        if mode != "full" and _fetched_within_cooldown(row["last_fetched"] if row else None, now_utc):
            skipped.append(symbol)  # tried recently, provider had nothing new
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


class _SipEmbargo(RuntimeError):
    """SIP end date still refused after retreating the max number of days."""


async def _fetch_pair(client: AlpacaClient, batch: list[str], start: str, end: str, feed: str):
    """(raw, adj, end_used). On a SIP-embargo 403 the request end is walked back
    one day at a time (down to `start`) before giving up."""
    cur = end
    for _ in range(_SIP_EMBARGO_MAX_RETREAT + 1):
        try:
            raw = await client.get_stock_bars(batch, start, cur, "raw", feed=feed)
            adj = await client.get_stock_bars(batch, start, cur, "all", feed=feed)
            return raw, adj, cur
        except FetchHTTPError as exc:
            if getattr(exc, "status", None) != 403 or _SIP_EMBARGO_MARKER not in str(exc).lower():
                raise
            prev = (date.fromisoformat(cur) - timedelta(days=1)).isoformat()
            if prev < start:
                raise _SipEmbargo(str(exc)) from exc
            cur = prev
    raise _SipEmbargo("SIP end refused after retreating the maximum number of days")


async def run_asset_prices(
    conn: sqlite3.Connection, run_id: int, mode: str, scope: str, scope_arg: str | None
) -> None:
    feed = get_settings().alpaca_price_feed
    targets = _targets(conn, scope, scope_arg)
    runs.set_planned(conn, run_id, len(targets))
    now_utc = _now_utc()
    data_end = _data_end(now_utc)
    end = data_end.isoformat()

    skipped, groups = _plan(conn, targets, mode, now_utc, data_end)
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
                    raw, adj, end_used = await _fetch_pair(client, batch, start, end, feed)
                except _SipEmbargo:
                    # nothing available yet on the free plan — not an error;
                    # the cooldown + "already current" checks will retry later
                    per = int((time.monotonic() - t0) * 1000 / len(batch))
                    for j, symbol in enumerate(batch):
                        _touch_fetched(conn, symbol)
                        runs.finish_target(conn, run_id, symbol, status="skipped",
                                           requests=2 if j == 0 else 0, duration_ms=per,
                                           error="SIP data not yet released for this range")
                    continue
                except Exception as exc:  # noqa: BLE001 - the whole batch failed
                    per = int((time.monotonic() - t0) * 1000 / len(batch))
                    for j, symbol in enumerate(batch):
                        runs.finish_target(conn, run_id, symbol, status="error",
                                           requests=2 if j == 0 else 0, duration_ms=per,
                                           error=str(exc)[:300])
                    continue

                per = int((time.monotonic() - t0) * 1000 / len(batch))
                if end_used != end:
                    conn.execute("UPDATE fetch_runs SET current_target = ? WHERE id = ?",
                                 (f"{label} (SIP end → {end_used})", run_id))
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
