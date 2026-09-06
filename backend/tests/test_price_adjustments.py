"""Incremental price repair with deterministic provider data; no network."""
import asyncio
from datetime import datetime, timezone

import pytest

from app.db.connection import get_connection
from app.features.data_management import prices, runs, worker


def bar(day, price):
    return {"t": day + "T00:00:00Z", "o": price, "h": price + 2,
            "l": price - 2, "c": price + 1, "v": 1000}


@pytest.fixture
def market(client, monkeypatch):
    days = ["2024-01-02", "2024-06-03", "2024-06-04", "2024-06-05"]
    raw = [bar(day, 100 + i) for i, day in enumerate(days)]
    calls = []
    config = {"factor": .5, "repair_error": None, "drop_adjusted": False, "empty": False}
    monkeypatch.setattr(prices, "_now_utc", lambda: datetime(2024, 6, 6, 12, tzinfo=timezone.utc))

    class Provider:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_stock_bars(self, symbols, start, end, adjustment, **kwargs):
            calls.append((tuple(symbols), start, end, adjustment))
            repair = start == "2016-01-01" and symbols == ["AAA"]
            if repair and config["repair_error"] == "network":
                raise RuntimeError("Provider unavailable during repair")
            result = {}
            for symbol in symbols:
                rows = [dict(b) for b in raw if start <= b["t"][:10] <= end]
                if repair and config["repair_error"] == "incomplete":
                    rows = rows[1:]
                if adjustment == "all":
                    if symbol == "AAA":
                        for b in rows:
                            for field in ("o", "h", "l", "c"):
                                b[field] *= config["factor"]
                    if config["drop_adjusted"]:
                        rows = rows[:-1]
                result[symbol] = [] if config["empty"] else rows
            return result

    monkeypatch.setattr(prices, "AlpacaClient", Provider)
    with get_connection() as conn:
        for symbol in ("AAA", "BBB"):
            conn.execute("INSERT INTO assets (symbol, asset_class, status, active) VALUES (?, 'us_equity', 'active', 1)", (symbol,))
            prices._write(conn, symbol, prices._merge(raw[:-1], raw[:-1], "sip"))
        conn.execute("UPDATE price_bar_stats SET last_fetched = '2000-01-01T00:00:00Z'")

    def run(mode="incremental"):
        with get_connection() as conn:
            run_id = runs.create_run(conn, "asset_prices", mode)
        asyncio.run(worker._run_job(worker.Job(run_id, "asset_prices", mode, "all", None)))
        return client.get(f"/api/data/runs/{run_id}").json(), {
            r["target"]: r for r in client.get(f"/api/data/runs/{run_id}/items").json()
        }

    def stored(symbol):
        with get_connection() as conn:
            return [tuple(r) for r in conn.execute(
                "SELECT date, close, adj_close FROM price_bars WHERE symbol = ? ORDER BY date", (symbol,)
            )]

    return config, calls, run, stored


@pytest.mark.parametrize("factor", [.5, .997])
def test_split_or_dividend_repairs_only_changed_symbol(market, factor):
    config, calls, run, stored = market
    config["factor"] = factor
    status, items = run()
    assert status["status"] == "succeeded"
    assert len(calls) == 4  # one overlap batch + one full-history pair for AAA
    assert calls[0][0] == ("AAA", "BBB")
    assert calls[0][1] == "2024-05-05"
    assert calls[2][0] == ("AAA",) and calls[2][1] == "2016-01-01"
    assert stored("AAA")[0][2] == pytest.approx(101 * factor)
    assert stored("BBB")[0][2] == 101
    assert len(stored("AAA")) == len(stored("BBB")) == 4
    assert items["AAA"]["note"] == "Adjusted prices changed; full history refreshed"
    assert items["AAA"]["coverage_start"] == "2024-01-02"
    assert items["BBB"]["note"] is None
    assert status["requests_made"] == 4


def test_unchanged_adjustments_only_fetch_overlap_and_tail(market):
    config, calls, run, stored = market
    config["factor"] = 1
    status, items = run()
    assert status["status"] == "succeeded"
    assert len(calls) == 2
    assert all(item["note"] is None for item in items.values())
    assert len(stored("AAA")) == 4
    # A rapid repeat makes no provider calls and never duplicates dates.
    _, items = run()
    assert all(item["status"] == "skipped" for item in items.values())
    assert len(calls) == 2 and len(stored("AAA")) == 4


def test_adjustments_are_checked_without_a_new_trading_day(market, monkeypatch):
    _, calls, run, stored = market
    monkeypatch.setattr(prices, "_now_utc", lambda: datetime(2024, 6, 5, 12, tzinfo=timezone.utc))
    status, items = run()
    assert status["status"] == "succeeded"
    assert items["AAA"]["note"]
    assert len(calls) == 4
    assert stored("AAA")[-1][0] == "2024-06-04"
    assert stored("AAA")[0][2] == 50.5


@pytest.mark.parametrize("failure", ["network", "incomplete"])
def test_failed_repair_preserves_all_stored_prices_and_can_retry(market, failure):
    config, calls, run, stored = market
    before = stored("AAA")
    config["repair_error"] = failure
    status, items = run()
    assert status["status"] == "failed"
    assert items["AAA"]["status"] == "error"
    assert stored("AAA") == before  # neither the changed overlap nor new tail is committed
    assert len(stored("BBB")) == 4
    config["repair_error"] = None
    status, items = run()
    assert status["status"] == "succeeded"
    assert items["AAA"]["note"]
    assert stored("AAA")[0][2] == 50.5


@pytest.mark.parametrize("failure", ["drop_adjusted", "empty"])
def test_missing_provider_data_does_not_overwrite_or_claim_a_successful_check(market, failure):
    config, _, run, stored = market
    before = stored("AAA")
    config[failure] = True
    status, items = run()
    assert status["status"] == "failed"
    assert items["AAA"]["status"] == "error"
    assert stored("AAA") == before


def test_full_fetch_bypasses_cooldown_without_a_second_repair(market):
    _, calls, run, stored = market
    with get_connection() as conn:
        conn.execute("UPDATE price_bar_stats SET last_fetched = '2024-06-06T11:59:00Z'")
    status, items = run("full")
    assert status["status"] == "succeeded"
    assert len(calls) == 2 and calls[0][1] == "2016-01-01"
    assert stored("AAA")[0][2] == 50.5
    assert items["AAA"]["note"] is None


def test_new_symbol_gets_full_history_on_incremental_fetch(market):
    _, calls, run, stored = market
    with get_connection() as conn:
        conn.execute("INSERT INTO assets (symbol, asset_class, status, active) VALUES ('NEW', 'us_equity', 'active', 1)")
    status, _ = run()
    assert status["status"] == "succeeded"
    assert len(stored("NEW")) == 4
    assert any(c[0] == ("NEW",) and c[1] == "2016-01-01" for c in calls)
