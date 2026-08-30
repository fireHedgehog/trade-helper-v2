"""Signal engine — determinism, a hand-checked Donchian breakout, metrics
sanity, and the config / run / timing API round-trip."""

from __future__ import annotations

import math
from datetime import date, timedelta


def _bars(closes: list[float], start: str = "2020-01-01") -> list[dict]:
    d = date.fromisoformat(start)
    out = []
    for i, c in enumerate(closes):
        out.append({"date": (d + timedelta(days=i)).isoformat(),
                    "o": closes[i - 1] if i else c, "h": c + 0.5, "l": c - 0.5,
                    "c": c, "v": 1_000_000})
    return out


def _ramp_then_drop() -> list[dict]:
    closes = [100.0] * 40 + [100.0 + 1.5 * i for i in range(1, 21)] + \
             [130.0 - 2.0 * i for i in range(1, 16)]
    return _bars(closes)


def test_engine_is_deterministic():
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams

    bars = _ramp_then_drop()
    p = SignalParams()
    r1, r2 = run(bars, p), run(bars, p)
    assert r1.trades == r2.trades
    assert r1.daily == r2.daily


def test_donchian_breakout_enters_long_and_exits():
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams

    r = run(_ramp_then_drop(), SignalParams())
    longs = [t for t in r.trades if t["direction"] == "long"]
    assert longs, "the 40-flat -> ramp series must trigger a long breakout"
    first = longs[0]
    assert 100.0 <= first["entry_price"] <= 106.0
    closed = [t for t in r.trades if t["exit_date"] is not None]
    assert closed, "the drop must close the long"
    assert closed[0]["exit_reason"] in {"stop_initial", "stop_trailing", "channel_reversal"}
    assert closed[0]["bars_held"] >= 1


def test_open_position_has_no_exit_and_metrics_are_sane():
    from app.features.signals import metrics
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams

    # ramp that never reverses -> ends still-open
    bars = _bars([100.0] * 40 + [100.0 + 1.2 * i for i in range(1, 60)])
    r = run(bars, SignalParams())
    opens = [t for t in r.trades if t["exit_date"] is None]
    assert len(opens) == 1
    assert opens[0]["exit_price"] is None and opens[0]["exit_reason"] is None

    m = metrics.summarise(r.trades, r.daily, bars)
    ts = m["trade_stats"]
    assert ts["open_position"] == "long"
    if ts["win_rate"] is not None:
        assert 0.0 <= ts["win_rate"] <= 1.0
    pf = ts["profit_factor"]
    assert pf is None or pf >= 0.0
    assert m["strategy"]["max_drawdown"] is None or m["strategy"]["max_drawdown"] <= 0.0


# ---- API ----

def _seed_bars(conn, symbol: str, n: int = 420) -> None:
    d = date(2024, 1, 1)
    rows, k = [], 0
    px = 50.0
    while k < n:
        if d.weekday() < 5:
            # gently trending with a mid wobble so the rule takes >1 trade
            px *= 1.0 + (0.004 if (k // 40) % 2 == 0 else -0.003)
            rows.append((symbol, d.isoformat(), px, px * 1.01, px * 0.99, px, 1_000_000,
                         px, px * 1.01, px * 0.99, px, 1_000_000))
            k += 1
        d += timedelta(days=1)
    conn.execute("INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
                 "VALUES (?,?, 'us_equity', 'active', 1)", (symbol, f"{symbol} Inc"))
    conn.executemany(
        "INSERT OR REPLACE INTO price_bars (symbol, date, open, high, low, close, volume, "
        "adj_open, adj_high, adj_low, adj_close, adj_volume) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    last = rows[-1]
    conn.execute(
        "INSERT OR REPLACE INTO price_bar_stats (symbol, bar_count, first_date, last_date, "
        "last_close, last_fetched) VALUES (?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        (symbol, len(rows), rows[0][1], last[1], last[5]),
    )


def test_engine_respects_allow_short():
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams

    # 40 flat then a slide down -> would break the 20-day low (short signal)
    bars = _bars([100.0] * 40 + [100.0 - 1.5 * i for i in range(1, 30)])
    both = run(bars, SignalParams(allow_long=True, allow_short=True))
    long_only = run(bars, SignalParams(allow_long=True, allow_short=False))
    assert any(t["direction"] == "short" for t in both.trades)
    assert all(t["direction"] == "long" for t in long_only.trades)


def test_config_round_trip(client):
    got = client.get("/api/signals/config").json()
    assert got["params"]["entry_len"] == 20
    assert got["engine_version"] == "donchian-1"

    got["params"]["entry_len"] = 30
    put = client.put("/api/signals/config", json={"name": "tuned", "params": got["params"]})
    assert put.status_code == 200
    assert client.get("/api/signals/config").json()["params"]["entry_len"] == 30


def test_run_then_timing_and_stale_flag(client):
    from app.db.connection import get_connection

    with get_connection() as conn:
        _seed_bars(conn, "TREND")

    ran = client.post("/api/signals/run", json={"symbol": "TREND"}).json()
    assert ran["status"] == "ok"
    assert isinstance(ran["trades"], list)
    assert "trade_stats" in ran["metrics"]
    # `daily` is returned so the frontend can recompute a long-only / short-only view
    assert len(ran["daily"]) == len(ran["bars"])
    assert all(d["state"] in (-1, 0, 1) for d in ran["daily"])
    assert len(ran["markers"]) >= 2 * len([t for t in ran["trades"] if t["exit_date"]])

    cached = client.get("/api/signals/timing/TREND").json()
    assert cached["computed_at"] == ran["computed_at"]
    assert cached["stale"] is False

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_bars (symbol, date, open, high, low, close, volume, adj_close) "
            "VALUES ('TREND','2099-01-01',1,1,1,1,1,1)"
        )
        conn.execute("UPDATE price_bar_stats SET last_date='2099-01-01' WHERE symbol='TREND'")

    assert client.get("/api/signals/timing/TREND").json()["stale"] is True


def test_timing_not_computed_by_default(client):
    body = client.get("/api/signals/timing/NOPE").json()
    assert body["status"] == "not_computed"


def test_run_rejects_thin_history(client):
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
                     "VALUES ('THIN','Thin','us_equity','active',1)")
        for i in range(10):
            conn.execute("INSERT INTO price_bars (symbol,date,open,high,low,close,volume,adj_close) "
                         "VALUES ('THIN',?,1,1,1,1,1,1)", (f"2024-01-{i + 1:02d}",))

    assert client.post("/api/signals/run", json={"symbol": "THIN"}).status_code == 400


def test_board_not_computed_by_default(client):
    body = client.get("/api/signals/board").json()
    assert body["status"] == "not_computed"
    # the hard-coded watchlist is always present (sectioned), even before a run
    titles = [s["title"] for s in body["watchlist"]]
    assert "Indices" in titles and "Mega-cap 7" in titles
    syms = {r["symbol"] for s in body["watchlist"] for r in s["rows"]}
    assert {"SPY", "QQQ", "IWM", "AAPL", "NVDA", "GLD", "USO", "BTC/USD"} <= syms


def test_universe_run_populates_the_board(client):
    import time

    from app.db.connection import get_connection

    with get_connection() as conn:
        _seed_bars(conn, "SPY", n=300)          # gentle up/down -> in a position
        _seed_bars(conn, "BRK", n=300)
        # a too-short name must be skipped, not fail the run
        conn.execute("INSERT OR REPLACE INTO assets (symbol, name, asset_class, status, active) "
                     "VALUES ('TINY','Tiny','us_equity','active',1)")
        for i in range(20):
            conn.execute("INSERT INTO price_bars (symbol,date,open,high,low,close,volume,adj_close) "
                         "VALUES ('TINY',?,1,1,1,1,1,1)", (f"2024-02-{i + 1:02d}",))

    run_id = client.post("/api/signals/run-universe").json()["run_id"]
    for _ in range(120):
        st = client.get(f"/api/data/runs/{run_id}").json()
        if st["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert st["status"] == "succeeded", st

    board = client.get("/api/signals/board").json()
    assert board["status"] == "ok"
    total = board["counts"]["long"] + board["counts"]["short"] + board["counts"]["flat"]
    assert total >= 2  # SPY + BRK computed, TINY skipped
    # long / short lists are sorted newest-entry first
    for bucket in (board["long"], board["short"]):
        dates = [r["state_since"] for r in bucket if r["state_since"]]
        assert dates == sorted(dates, reverse=True)

    # a symbol only in the universe run is still reachable from Timing
    seen = {r["symbol"] for r in board["long"] + board["short"] + board["flat"]}
    some = next(iter(seen))
    t = client.get(f"/api/signals/timing/{some}").json()
    assert t["status"] == "ok"
    assert t["run_scope"] == "universe"
    assert t["chart_cached"] is False
    assert "trade_stats" in t["metrics"]
