"""Data Management: schema seeds, browse endpoints, and a fetch run with a
monkeypatched provider handler (no network)."""

from __future__ import annotations

import pytest


def test_macro_catalog_seeded(client):
    rows = client.get("/api/data/macro").json()
    assert len(rows) == 30  # 28 FRED macro series + WTI + Brent oil (0006)
    cats = {r["category"] for r in rows}
    assert {"inflation", "rates", "growth", "labor", "risk", "money-fx"} <= cats
    by_id = {r["series_id"]: r for r in rows}
    assert by_id["CPIAUCSL"]["short_label"]
    assert by_id["CPIAUCSL"]["point_count"] in (None, 0)  # nothing fetched yet


def test_commodity_catalog_seeded(client):
    rows = client.get("/api/data/commodities").json()
    assert {r["instrument"] for r in rows} == {"WTI", "BRENT", "NATGAS"}


def test_assets_browse_empty(client):
    body = client.get("/api/data/assets").json()
    assert body == {"rows": [], "total": 0, "page": 1, "page_size": 100}


def test_page_size_capped(client):
    body = client.get("/api/data/assets?page_size=9999")
    assert body.status_code == 422  # FastAPI Query(le=200) rejects it


def test_start_run_rejects_bad_kind(client):
    r = client.post("/api/data/runs", json={"kind": "nonsense"})
    assert r.status_code == 422


def test_start_run_single_requires_arg(client):
    r = client.post("/api/data/runs", json={"kind": "asset_prices", "scope": "single"})
    assert r.status_code == 400


def test_fetch_run_end_to_end_with_stub(client, monkeypatch):
    """Submit a macro run whose handler is replaced by a no-network stub that
    writes one observation and one run item."""
    from app.features.data_management import runs, worker

    async def fake_macro(conn, run_id, mode):
        runs.set_planned(conn, run_id, 1)
        runs.start_target(conn, run_id, "CPIAUCSL")
        conn.execute(
            "INSERT INTO macro_observations (series_id, date, value) VALUES ('CPIAUCSL','2024-01-01',300.0)"
        )
        runs.finish_target(conn, run_id, "CPIAUCSL", status="ok", rows=1, requests=2,
                           coverage_start="2024-01-01", coverage_end="2024-01-01")

    monkeypatch.setattr("app.features.data_management.macro.run_macro", fake_macro)

    run_id = client.post("/api/data/runs", json={"kind": "macro"}).json()["run_id"]

    # Worker runs on the app event loop; poll until it settles.
    import time

    for _ in range(50):
        status = client.get(f"/api/data/runs/{run_id}").json()
        if status["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)

    assert status["status"] == "succeeded"
    assert status["completed_targets"] == 1
    assert status["rows_written"] == 1

    items = client.get(f"/api/data/runs/{run_id}/items").json()
    assert items[0]["target"] == "CPIAUCSL"
    assert items[0]["status"] == "ok"

    obs = client.get("/api/data/macro/CPIAUCSL/observations").json()
    assert obs["total"] == 1
    assert obs["rows"][0]["value"] == 300.0


def test_duplicate_submit_is_deduped(client, monkeypatch):
    """A second submit of the same kind while one is active attaches to it."""
    import asyncio

    async def slow_macro(conn, run_id, mode):
        from app.features.data_management import runs

        runs.set_planned(conn, run_id, 1)
        await asyncio.sleep(0.5)

    monkeypatch.setattr("app.features.data_management.macro.run_macro", slow_macro)

    first = client.post("/api/data/runs", json={"kind": "macro"}).json()
    second = client.post("/api/data/runs", json={"kind": "macro"}).json()

    assert first["run_id"] == second["run_id"]
    assert second["deduped"] is True

    active = client.get("/api/data/runs/active").json()
    assert any(r["id"] == first["run_id"] for r in active)

    import time

    for _ in range(50):
        if client.get(f"/api/data/runs/{first['run_id']}").json()["status"] not in (
            "queued", "running"
        ):
            break
        time.sleep(0.1)


def test_memberships_sync_with_stubbed_scrapers(client, monkeypatch):
    """Stub the issuer scrapers; check symbol_memberships, group counts, and
    that assets.sector is derived from the single sector-SPDR membership."""
    from app.db.connection import get_connection
    from app.features.data_management import memberships as mem

    with get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) VALUES (?,?,?,?,1)",
            [("AAPL", "Apple", "us_equity", "active"), ("XOM", "Exxon", "us_equity", "active"),
             ("JPM", "JPMorgan", "us_equity", "active")],
        )

    async def fake_ssga(client_, ticker):
        data = {
            "SPY": [{"symbol": "AAPL", "name": "Apple", "weight": 7.0},
                    {"symbol": "XOM", "name": "Exxon", "weight": 1.0},
                    {"symbol": "JPM", "name": "JPMorgan", "weight": 1.2}],
            "XLK": [{"symbol": "AAPL", "name": "Apple", "weight": 12.0}],
            "XLE": [{"symbol": "XOM", "name": "Exxon", "weight": 22.0}],
            "XLF": [{"symbol": "JPM", "name": "JPMorgan", "weight": 10.0}],
        }
        return data.get(ticker, [])

    async def fake_ndx(client_):
        return [{"symbol": "AAPL", "name": "Apple", "weight": None, "market_cap": 3.5e12}]

    async def fake_ish(client_, url):
        return [{"symbol": "AAPL", "name": "Apple", "weight": 9.0}]

    async def fake_ark(client_, url, fund):
        return [{"symbol": "RKLB", "name": "Rocket Lab", "weight": 8.0}]

    monkeypatch.setattr(mem, "fetch_ssga", fake_ssga)
    monkeypatch.setattr(mem, "fetch_nasdaq100", fake_ndx)
    monkeypatch.setattr(mem, "fetch_ishares", fake_ish)
    monkeypatch.setattr(mem, "fetch_ark", fake_ark)

    run_id = client.post("/api/data/runs", json={"kind": "memberships"}).json()["run_id"]
    import time

    for _ in range(100):
        s = client.get(f"/api/data/runs/{run_id}").json()
        if s["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert s["status"] == "succeeded", s

    groups = {g["group_key"]: g for g in client.get("/api/data/memberships").json()}
    assert groups["SP500"]["member_count"] == 3
    assert groups["XLK"]["member_count"] == 1
    assert groups["XLE"]["gics_sector"] == "Energy"

    detail = client.get("/api/data/assets/AAPL").json()
    assert detail["asset"]["sector"] == "Information Technology"
    assert detail["asset"]["market_cap"] == 3_500_000_000_000
    xom = client.get("/api/data/assets/XOM").json()
    assert xom["asset"]["sector"] == "Energy"


def test_memberships_sync_folds_new_index_members_into_active_universe(client, monkeypatch):
    """A name that is not in the hand seed but appears in a scraped auto-active
    group (here NDX) is switched on for price fetching by the sync."""
    from app.db.connection import get_connection
    from app.features.data_management import memberships as mem

    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
            "VALUES ('NEWCO', 'New Co', 'us_equity', 'active', 0)"
        )

    async def fake_ndx(client_):
        return [{"symbol": "NEWCO", "name": "New Co", "weight": None, "market_cap": 5e10}]

    async def empty_ssga(client_, ticker):
        return []

    async def empty_list(client_, url):
        return []

    async def empty_ark(client_, url, fund):
        return []

    monkeypatch.setattr(mem, "fetch_nasdaq100", fake_ndx)
    monkeypatch.setattr(mem, "fetch_ssga", empty_ssga)
    monkeypatch.setattr(mem, "fetch_ishares", empty_list)
    monkeypatch.setattr(mem, "fetch_ark", empty_ark)

    run_id = client.post("/api/data/runs", json={"kind": "memberships"}).json()["run_id"]
    import time

    for _ in range(100):
        s = client.get(f"/api/data/runs/{run_id}").json()
        if s["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert s["status"] == "succeeded", s

    items = {r["target"]: r["status"] for r in client.get(f"/api/data/runs/{run_id}/items").json()}
    assert items["recompute-universe"] == "ok"
    assert client.get("/api/data/assets/NEWCO").json()["asset"]["active"] == 1


def test_asset_prices_skips_recent_and_batches_the_rest(client, monkeypatch):
    """A symbol fetched within the retry cooldown is skipped without any
    provider call; symbols that share a start date go out in one raw + one
    adjusted request, not a pair per symbol."""
    import time
    from datetime import datetime, timedelta, timezone

    from app.db.connection import get_connection
    from app.features.data_management import prices

    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    calls: list[tuple[tuple[str, ...], str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get_stock_bars(self, symbols, start, end, adjustment, **kw):
            calls.append((tuple(symbols), adjustment))
            return {}

    monkeypatch.setattr(prices, "AlpacaClient", FakeClient)

    with get_connection() as conn:
        conn.execute("BEGIN")
        for sym in ("AAA", "BBB", "CCC"):
            conn.execute(
                "INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
                "VALUES (?,?, 'us_equity', 'active', 1)",
                (sym, f"{sym} Inc"),
            )
        # AAA was pulled minutes ago -> must be skipped with zero calls.
        # BBB + CCC share a last_date -> one batch covers both.
        conn.executemany(
            "INSERT INTO price_bar_stats (symbol, bar_count, first_date, last_date, "
            "last_close, last_fetched) VALUES (?,?,?,?,?,?)",
            [
                ("AAA", 1, "2024-01-01", "2024-06-01", 1.0, recent),
                ("BBB", 1, "2024-01-01", "2024-06-01", 1.0, "2020-01-01T00:00:00.000Z"),
                ("CCC", 1, "2024-01-01", "2024-06-01", 1.0, "2020-01-01T00:00:00.000Z"),
            ],
        )
        conn.execute("COMMIT")

    run_id = client.post("/api/data/runs", json={"kind": "asset_prices"}).json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/data/runs/{run_id}").json()
        if st["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert st["status"] == "succeeded", st

    items = {r["target"]: r["status"] for r in client.get(f"/api/data/runs/{run_id}/items").json()}
    assert items["AAA"] == "skipped"
    assert items["BBB"] == "ok"
    assert items["CCC"] == "ok"

    assert all("AAA" not in syms for syms, _ in calls)
    assert len(calls) == 2  # one batch: raw + adjusted
    assert sorted(adj for _, adj in calls) == ["all", "raw"]
    assert set(calls[0][0]) == {"BBB", "CCC"}

    # the run's request counter reflects the batch, not one pair per symbol
    assert client.get(f"/api/data/runs/{run_id}").json()["requests_made"] == 2


def test_option_snapshots_store_a_small_grid(client, monkeypatch):
    """Stub the chain; the handler keeps only the 6-tenor x 7-moneyness grid,
    not every strike/expiry it was handed."""
    import time
    from datetime import datetime, timedelta, timezone

    from app.db.connection import get_connection
    from app.features.data_management import options as opt

    spot = 100.0
    today = datetime.now(timezone.utc).date()  # match options._today (UTC, not local)
    # expirations that land near the 7/30/60/90/120/180 ladder, plus noise
    exps = [today + timedelta(days=d) for d in (7, 21, 35, 65, 95, 125, 150, 185)]
    strikes = [round(70 + 2.5 * i, 1) for i in range(25)]  # 70.0 .. 130.0

    def occ(u, e: date, cp: str, k: float) -> str:
        return f"{u}{e:%y%m%d}{cp}{int(round(k * 1000)):08d}"

    chain: dict[str, dict] = {}
    for e in exps:
        for k in strikes:
            for cp in ("C", "P"):
                chain[occ("TESTX", e, cp, k)] = {
                    "latestQuote": {"bp": 1.0, "ap": 1.2},
                    "latestTrade": {"p": 1.1},
                    "dailyBar": {"v": 10},
                    "greeks": {"delta": 0.5, "gamma": 0.01, "theta": -0.02, "vega": 0.1, "rho": 0.0},
                    "impliedVolatility": 0.25,
                }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get_option_snapshots(self, underlying, params):
            assert underlying == "TESTX"
            return chain

    monkeypatch.setattr(opt, "AlpacaClient", FakeClient)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_bars (symbol, date, open, high, low, close, volume) "
            "VALUES ('TESTX', ?, ?, ?, ?, ?, 1)",
            (today.isoformat(), spot, spot, spot, spot),
        )
        conn.execute("INSERT INTO options_research_set (underlying, bucket) VALUES ('TESTX','test')")

    run_id = client.post("/api/data/runs", json={"kind": "option_snapshots"}).json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/data/runs/{run_id}").json()
        if st["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert st["status"] == "succeeded", st

    items = {r["target"]: r["status"] for r in client.get(f"/api/data/runs/{run_id}/items").json()}
    assert items["TESTX"] == "ok"
    # the migration-0003 seed names have no price bars in this fresh DB -> skipped, not failed
    assert items["SPY"] == "skipped"

    from app.db.connection import get_connection as gc
    with gc() as conn:
        rows = conn.execute(
            "SELECT DISTINCT expiration FROM option_chain_snapshots WHERE underlying='TESTX'"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM option_chain_snapshots WHERE underlying='TESTX'"
        ).fetchone()[0]
        sd = conn.execute(
            "SELECT DISTINCT snapshot_date FROM option_chain_snapshots WHERE underlying='TESTX'"
        ).fetchall()

    assert len(rows) == 6                    # 6 tenors picked from 8 expirations
    assert 6 * 6 <= total <= 6 * 8           # ~7-8 grid legs per expiration
    assert sd[0][0] == today.isoformat()

    stats = {r["underlying"]: r for r in client.get("/api/data/options").json()}
    assert stats["TESTX"]["last_day_rows"] == total
    assert stats["TESTX"]["snapshot_days"] == 1


@pytest.mark.parametrize("kind", ["asset_catalog", "asset_prices", "crypto_bars",
                                  "commodity_prices", "macro", "memberships",
                                  "option_snapshots"])
def test_all_kinds_accepted(client, monkeypatch, kind):
    # Replace every handler with a no-op so we only test the submit/queue path.
    async def noop(*a, **k):
        pass

    for mod in ("catalog.run_asset_catalog", "prices.run_asset_prices",
                "crypto.run_crypto_bars", "commodities.run_commodities", "macro.run_macro",
                "memberships.run_memberships", "options.run_option_snapshots"):
        monkeypatch.setattr(f"app.features.data_management.{mod}", noop)

    r = client.post("/api/data/runs", json={"kind": kind, "scope_arg": "AAPL"})
    assert r.status_code == 200
    assert "run_id" in r.json()
