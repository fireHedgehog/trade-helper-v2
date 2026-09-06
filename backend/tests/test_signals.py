"""Signal engine — determinism, a hand-checked Donchian breakout, metrics
sanity, and the config / run / timing API round-trip."""

from __future__ import annotations

import math

import pytest
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
    assert got["engine_version"] == "donchian-2"

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


# Executions use only information available when the order can fill.
def _execution_bars(*sessions):
    bars = _bars([100.0] * 35)
    for op, hi, lo, cl in sessions:
        d = date.fromisoformat(bars[-1]["date"]) + timedelta(days=1)
        bars.append({"date": d.isoformat(), "o": op, "h": hi, "l": lo, "c": cl, "v": 1000})
    return bars


def test_latest_breakout_is_pending_until_next_open():
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams
    bars = _execution_bars((100, 103, 99.8, 102))
    r = run(bars, SignalParams())
    assert r.trades == []
    assert r.pending_action == {"action": "enter", "direction": "long",
                                "signal_date": bars[-1]["date"], "fill_at": "open_next",
                                "reason": "breakout"}
    filled = run(_execution_bars((100, 103, 99.8, 102), (120, 121, 119, 120)), SignalParams())
    assert filled.pending_action is None
    assert filled.trades[0]["entry_price"] == 120
    assert filled.trades[0]["entry_date"] > r.pending_action["signal_date"]


@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("costs", [False, True])
def test_equity_reconciles_to_fills_including_entry_gap_exit_gap_and_costs(short, costs):
    from app.features.signals.engine import run, compound
    from app.features.signals.params import SignalParams
    bars = _execution_bars((100, 103, 99.8, 102), (120, 121, 119, 120), (90, 91, 89, 90))
    if short:
        bars = [{**b, "o": 200-b["o"], "h": 200-b["l"], "l": 200-b["h"], "c": 200-b["c"]} for b in bars]
    p = SignalParams(cost_bps=5 if costs else 0, slippage_atr=0.05 if costs else 0)
    r = run(bars, p)
    trade = r.trades[0]
    assert len(r.trades) == 1 and trade["exit_date"] is not None
    assert trade["direction"] == ("short" if short else "long")
    expected_gross = -0.375 if short else -0.25
    assert trade["return_pct"] <= expected_gross + 1e-12
    assert compound([d["strat_ret"] for d in r.daily])[-1] - 1 == pytest.approx(trade["return_pct"])
    assert r.daily[-2]["strat_ret"] <= 0  # no return earned before the opening entry
    assert r.daily[-1]["strat_ret"] < 0   # the exit gap is a real loss
    if not costs:
        assert trade["return_pct"] == pytest.approx(expected_gross)


@pytest.mark.parametrize("trail_mode", ["chandelier", "atr_trail"])
@pytest.mark.parametrize("short", [False, True])
def test_close_derived_stop_only_applies_next_session(trail_mode, short):
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams
    bars = _execution_bars((100, 103, 99.8, 102), (103, 104, 102, 103), (103, 120, 102, 119))
    if short:
        bars = [{**b, "o": 200-b["o"], "h": 200-b["l"], "l": 200-b["h"], "c": 200-b["c"]} for b in bars]
    p = SignalParams(trail_mode=trail_mode, cost_bps=0, slippage_atr=0)
    r = run(bars, p)
    assert len(r.trades) == 1 and r.trades[0]["exit_date"] is None
    old_stop, new_stop = r.overlays["stop_line"][-2:]
    if short:
        assert old_stop > bars[-1]["h"] > new_stop
    else:
        assert old_stop < bars[-1]["l"] < new_stop
    # A subsequent session can execute the revised stop, including an opening gap.
    last = bars[-1]
    price = new_stop + (2 if short else -2)
    bars.append({"date": (date.fromisoformat(last["date"])+timedelta(days=1)).isoformat(),
                 "o": price, "h": price+0.1, "l": price-0.1, "c": price, "v": 1000})
    closed = run(bars, p).trades[0]
    assert closed["exit_date"] == bars[-1]["date"]
    assert closed["exit_price"] == price


def test_entry_session_stop_books_both_costs_and_loss():
    from app.features.signals.engine import run, compound
    from app.features.signals.params import SignalParams
    r = run(_execution_bars((100, 103, 99.8, 102), (120, 121, 100, 119)), SignalParams())
    t = r.trades[0]
    assert t["entry_date"] == t["exit_date"]
    assert t["return_pct"] < 0
    assert compound([d["strat_ret"] for d in r.daily])[-1] - 1 == pytest.approx(t["return_pct"])


def test_close_fill_does_not_earn_the_signal_bar_move():
    from app.features.signals.engine import run
    from app.features.signals.params import SignalParams
    r = run(_execution_bars((100, 103, 99.8, 102)), SignalParams(fill_at="close", cost_bps=0, slippage_atr=0))
    assert r.trades[0]["entry_price"] == 102
    assert r.daily[-1]["strat_ret"] == 0
    assert r.trades[0]["exit_date"] is None
    assert r.pending_action is None


def test_pending_channel_reversal_and_two_direction_accounting():
    from app.features.signals.engine import run, compound
    from app.features.signals.params import SignalParams
    bars = _execution_bars()
    for b in bars:
        b.update(h=110, l=90)
    for i, (op, hi, lo, cl) in enumerate([(100,112,99,111),(111,112,110,111),(111,112,88,89)]):
        bars.append({"date": (date.fromisoformat(bars[-1]["date"])+timedelta(days=1)).isoformat(),
                     "o":op,"h":hi,"l":lo,"c":cl,"v":1000})
    p = SignalParams(atr_stop_mult=6, chandelier_k=6, stop_and_reverse=True)
    r = run(bars, p)
    assert r.pending_action["action"] == "reverse"
    assert r.pending_action["direction"] == "short"
    assert r.trades[-1]["exit_date"] is None
    bars.append({"date": (date.fromisoformat(bars[-1]["date"])+timedelta(days=1)).isoformat(),
                 "o":88,"h":90,"l":85,"c":87,"v":1000})
    r = run(bars, p)
    assert len(r.trades) == 2
    assert r.trades[0]["exit_price"] == r.trades[1]["entry_price"] == 88
    assert r.trades[0]["exit_date"] == r.trades[1]["entry_date"]
    assert r.daily[-1]["long_ret"] != 0 and r.daily[-1]["short_ret"] != 0
    assert compound([d["long_ret"] for d in r.daily])[-1]-1 == pytest.approx(r.trades[0]["return_pct"])
    for d in r.daily:
        assert 1+d["strat_ret"] == pytest.approx((1+d["long_ret"])*(1+d["short_ret"]))


def test_pending_signal_survives_saved_run_and_reaches_board(client):
    from app.db.connection import get_connection
    from app.features.data_management import runs
    from app.features.signals import service
    with get_connection() as conn:
        _seed_bars(conn, "SPY", n=80)
        conn.execute("UPDATE price_bars SET open=100,high=101,low=99,close=100,adj_open=100,adj_high=101,adj_low=99,adj_close=100 WHERE symbol='SPY'")
        last_date = conn.execute("SELECT MAX(date) FROM price_bars WHERE symbol='SPY'").fetchone()[0]
        conn.execute("UPDATE price_bars SET high=103,close=102,adj_high=103,adj_close=102 WHERE symbol='SPY' AND date=?", (last_date,))
        # Use the worker's existing run record contract, with no provider calls.
        run_id = runs.create_run(conn, "signal_universe", "incremental", "all", None)
        service.run_universe(conn, run_id)
    timing = client.get('/api/signals/timing/SPY').json()
    board = client.get('/api/signals/board').json()
    assert timing['pending_action']['signal_date'] == last_date
    assert timing['state']['state'] == 'flat'
    assert next(r for r in board['pending'] if r['symbol']=='SPY')['pending_action']['action']=='enter'
    assert next(r for sec in board['watchlist'] for r in sec['rows'] if r['symbol']=='SPY')['pending_action']['action']=='enter'
