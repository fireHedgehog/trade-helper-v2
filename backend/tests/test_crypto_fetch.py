"""Coinbase pagination and safe replacement of stored crypto history."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.db.connection import get_connection
from app.features.data_management import crypto, runs, worker
from app.providers.clients import coinbase_client


def candle(day, close=101):
    return {"t": day + "T00:00:00Z", "o": 100, "h": max(105, close),
            "l": 95, "c": close, "v": 50}


def wire_candle(day):
    timestamp = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp())
    return [timestamp, 95, 105, 100, 101, 50]


def test_coinbase_paginates_sorts_and_excludes_unrequested_days(monkeypatch):
    calls = []
    start, end = date(2024, 1, 1), date(2024, 11, 1)

    async def response(client, limiter, url, *, params):
        calls.append((url, params))
        first = date.fromisoformat(params["start"][:10])
        last = date.fromisoformat(params["end"][:10])
        assert (last - first).days < 300
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        return [wire_candle(last + timedelta(days=1)), wire_candle(first)] + [
            wire_candle(day) for day in reversed(days)
        ]

    monkeypatch.setattr(coinbase_client, "paced_get_json", response)

    async def fetch():
        async with coinbase_client.CoinbaseClient() as provider:
            bars = await provider.get_crypto_bars("ETH/USD", start.isoformat(), end.isoformat())
            assert provider.requests_made == 2
            return bars

    bars = asyncio.run(fetch())
    assert len(bars) == (end - start).days + 1
    assert bars[0] == candle(start.isoformat())
    assert bars[-1] == candle(end.isoformat())
    assert all(url.endswith("/products/ETH-USD/candles") for url, _ in calls)


@pytest.mark.parametrize("row", [
    [1704067200, 110, 105, 100, 101, 50],  # impossible high/low
    [1704067200, 95, 105, 100, float("nan"), 50],
    [1704067201, 95, 105, 100, 101, 50],  # not a UTC daily boundary
])
def test_coinbase_rejects_invalid_candles(monkeypatch, row):
    async def response(*args, **kwargs):
        return [row]

    monkeypatch.setattr(coinbase_client, "paced_get_json", response)

    async def fetch():
        async with coinbase_client.CoinbaseClient() as provider:
            await provider.get_crypto_bars("BTC/USD", "2024-01-01", "2024-01-01")

    with pytest.raises(ValueError):
        asyncio.run(fetch())


@pytest.fixture
def market(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "crypto_history_start_date", "2024-01-01")
    monkeypatch.setattr(crypto, "_end_date", lambda: "2024-01-04")
    config = {"failure": None}
    calls = []

    class Provider:
        requests_made = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_crypto_bars(self, symbol, start, end, check_cancel):
            check_cancel()
            calls.append((symbol, start, end))
            self.requests_made += 1
            if config["failure"] == "network":
                raise RuntimeError("Coinbase unavailable")
            bars = [candle(f"2024-01-{i:02d}") for i in range(1, 5)
                    if start <= f"2024-01-{i:02d}" <= end]
            if config["failure"] == "gap":
                bars.pop(2)
            elif config["failure"] == "tail":
                bars.pop()
            elif config["failure"] == "start":
                bars = bars[2:]
            elif config["failure"] == "empty":
                bars = []
            elif config["failure"] == "cancel":
                raise runs.RunCancelled
            return bars

    monkeypatch.setattr(crypto, "CoinbaseClient", Provider)
    with get_connection() as conn:
        conn.execute("UPDATE crypto_assets SET active = 0")
        conn.execute("INSERT OR REPLACE INTO crypto_assets (symbol, active) VALUES ('BTC/USD', 1)")
        crypto._write(conn, "BTC/USD", [candle("2024-01-02", 80), candle("2024-01-03", 80)])
        conn.execute("UPDATE crypto_bars SET source = 'alpaca', trade_count = 123, vwap = 80")

    def stored():
        with get_connection() as conn:
            bars = [tuple(r) for r in conn.execute(
                "SELECT date, close, source, trade_count, vwap FROM crypto_bars ORDER BY date"
            )]
            stats = tuple(conn.execute("SELECT * FROM crypto_bar_stats WHERE symbol='BTC/USD'").fetchone())
        return bars, stats

    def run(mode="incremental"):
        with get_connection() as conn:
            run_id = runs.create_run(conn, "crypto_bars", mode)
        asyncio.run(worker._run_job(worker.Job(run_id, "crypto_bars", mode, "all", None)))
        return (client.get(f"/api/data/runs/{run_id}").json(),
                client.get(f"/api/data/runs/{run_id}/items").json())

    return config, calls, stored, run


@pytest.mark.parametrize("mode", ["incremental", "full"])
def test_fetch_replaces_old_source_then_updates_incrementally(market, mode):
    _, calls, stored, run = market
    result, items = run(mode)
    assert result["status"] == "succeeded"
    assert calls == [("BTC/USD", "2024-01-01", "2024-01-04")]
    bars, _ = stored()
    assert len(bars) == 4
    assert all(row[1:] == (101, "coinbase", None, None) for row in bars)
    assert items[0]["note"] == "Source changed to Coinbase; full history replaced"
    assert items[0]["coverage_end"] == "2024-01-04"
    result, _ = run()
    assert result["status"] == "succeeded"
    assert calls[-1] == ("BTC/USD", "2024-01-04", "2024-01-04")
    assert stored()[0] == bars
    run("full")
    assert calls[-1] == ("BTC/USD", "2024-01-01", "2024-01-04")


@pytest.mark.parametrize("failure", ["network", "gap", "tail", "start", "empty", "cancel"])
def test_incomplete_or_cancelled_replacement_retains_history(market, failure):
    config, _, stored, run = market
    before = stored()
    config["failure"] = failure
    result, _ = run()
    assert result["status"] == ("cancelled" if failure == "cancel" else "failed")
    assert stored() == before


def test_database_failure_rolls_back_replacement(market):
    _, _, stored, run = market
    before = stored()
    with get_connection() as conn:
        conn.execute("CREATE TRIGGER reject_crypto BEFORE INSERT ON crypto_bars "
                     "BEGIN SELECT RAISE(ABORT, 'test write failure'); END")
    result, _ = run()
    assert result["status"] == "failed"
    assert stored() == before


def test_new_product_can_start_after_requested_date():
    crypto._validate_coverage([candle("2024-01-03"), candle("2024-01-04")], None, "2024-01-04")
