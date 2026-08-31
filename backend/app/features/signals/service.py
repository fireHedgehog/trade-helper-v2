"""Signal orchestration.

- Timing (single symbol): `POST /run` computes + persists the full record
  (`signal_events` + `signal_symbol_stats` + `signal_chart`); `GET /timing`
  is a pure cache read.
- Trend (whole universe): `run_universe` loops every active symbol + the
  cross-asset trio + the watchlist, writing `signal_events` + `signal_symbol_stats`
  only (no per-symbol chart payload — the board doesn't need it; open Timing
  and press Run for the Donchian overlay / equity curve). `get_board` reads
  the last universe run back as three state tables.
"""

from __future__ import annotations

import json
import sqlite3
import time

from app.features.data_management import runs as fetch_runs
from app.features.signals import data as ohlc
from app.features.signals import engine, keylevels, metrics, repository as repo
from app.features.signals.params import ENGINE_VERSION, SignalParams
from app.features.signals.watchlist import TREND_WATCHLIST, TREND_WATCHLIST_SECTIONS

MIN_BARS = 60


# ---- config (single preset) ----

def get_config(conn: sqlite3.Connection) -> dict:
    cfg = repo.get_config(conn)
    params = SignalParams(**cfg["params"])
    return {"name": cfg["name"], "params": params.model_dump(),
            "engine_version": ENGINE_VERSION, "updated_at": cfg["updated_at"]}


def save_config(conn: sqlite3.Connection, params: SignalParams, name: str | None) -> dict:
    repo.save_config(conn, params.model_dump(), name)
    return get_config(conn)


# ---- run ----

def _board_state(bars: list[dict], trades: list[dict], overlays: dict) -> dict:
    last_close = bars[-1]["c"]
    last_date = bars[-1]["date"]
    open_tr = next((t for t in trades if t["exit_date"] is None), None)
    if open_tr:
        d = 1 if open_tr["direction"] == "long" else -1
        stops = [s for s in overlays["stop_line"] if s is not None]
        return {
            "state": open_tr["direction"], "state_since": open_tr["entry_date"],
            "entry_price": open_tr["entry_price"], "last_close": last_close, "last_date": last_date,
            "unrealized_pct": d * (last_close / open_tr["entry_price"] - 1.0),
            "current_stop": stops[-1] if stops else open_tr["initial_stop"],
        }
    last_exit = trades[-1]["exit_date"] if trades else None
    return {"state": "flat", "state_since": last_exit, "entry_price": None,
            "last_close": last_close, "last_date": last_date,
            "unrealized_pct": None, "current_stop": None}


def _full_result(bars: list[dict], params: SignalParams) -> dict:
    """Run the engine and assemble the whole Timing payload. Pure — no DB."""
    result = engine.run(bars, params)
    m = metrics.summarise(result.trades, result.daily, bars)
    state = _board_state(bars, result.trades, result.overlays)
    strat_eq = engine.compound([d["strat_ret"] for d in result.daily])
    equity = {
        "dates": [d["date"] for d in result.daily],
        "strat_equity": strat_eq,
        "bh_equity": engine.compound(engine.buy_hold_daily(bars)),
        "drawdown": engine.drawdown_curve(strat_eq),
    }
    levels = keylevels.key_levels(bars)
    if state["current_stop"] is not None:
        levels.append({"price": state["current_stop"], "label": "current stop", "kind": "stop"})
    # `daily` (per-bar exposure + cost-included return) lets the Timing page
    # recompute metrics / equity for a long-only or short-only view.
    payload = {"overlays": result.overlays, "equity": equity, "key_levels": levels,
               "daily": result.daily}
    return {"result": result, "metrics": m, "state": state, "payload": payload}


def preview(conn: sqlite3.Connection, symbol: str, params: SignalParams) -> dict:
    """Run one symbol with the supplied parameters and return the full Timing
    payload. Writes NOTHING — the Trend run owns the persisted signals; Timing
    is a live scratchpad."""
    symbol = ohlc.normalize_symbol(symbol)
    params = params.model_copy(update={"allow_long": True, "allow_short": True})
    bars = ohlc.load_ohlc(conn, symbol)
    if len(bars) < MIN_BARS:
        raise ValueError(f"{symbol}: only {len(bars)} bars — need >= {MIN_BARS} to run")
    fr = _full_result(bars, params)
    events = fr["result"].trades
    return {
        "status": "ok",
        "symbol": symbol,
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "preview": True,
        "engine_version": ENGINE_VERSION,
        "params": params.model_dump(),
        "stale": False,
        "newest_price_date": ohlc.latest_price_date(conn, symbol),
        "run_through_date": bars[-1]["date"],
        "bars": [{"time": b["date"], "open": b["o"], "high": b["h"], "low": b["l"],
                  "close": b["c"], "volume": b["v"]} for b in bars],
        "chart_cached": True,
        "run_scope": "preview",
        "overlays": fr["payload"]["overlays"],
        "key_levels": fr["payload"]["key_levels"],
        "equity": fr["payload"]["equity"],
        "daily": fr["payload"]["daily"],
        "markers": _markers(events),
        "trades": events,
        "state": {k: fr["state"][k] for k in
                  ("state", "state_since", "entry_price", "last_close", "unrealized_pct", "current_stop")},
        "metrics": fr["metrics"],
    }


def list_strategies(conn: sqlite3.Connection) -> dict:
    return {"strategies": repo.list_strategies(conn), "engine_version": ENGINE_VERSION}


def strategy_detail(conn: sqlite3.Connection, strategy_id: int) -> dict:
    s = repo.get_strategy(conn, strategy_id)
    if s is None:
        raise ValueError(f"no strategy {strategy_id}")
    return {**s, "symbols": repo.strategy_symbols(conn, strategy_id)}


def assign_strategy(conn: sqlite3.Connection, strategy_id: int, symbols: list[str]) -> dict:
    if repo.get_strategy(conn, strategy_id) is None:
        raise ValueError(f"no strategy {strategy_id}")
    norm = [ohlc.normalize_symbol(s) for s in symbols]
    changed = repo.assign_strategy(conn, strategy_id, norm)
    return {"assigned": changed, "symbols": repo.strategy_symbols(conn, strategy_id)}


def resolved_strategy(conn: sqlite3.Connection, symbol: str) -> dict:
    symbol = ohlc.normalize_symbol(symbol)
    return {"symbol": symbol, "strategy": repo.resolve_one(conn, symbol),
            "engine_version": ENGINE_VERSION}


def run_for_symbol(conn: sqlite3.Connection, symbol: str) -> dict:
    symbol = ohlc.normalize_symbol(symbol)
    # Always compute the full two-sided trade set. Long / short is a view
    # filter on the Timing page, not an engine input.
    resolved = repo.resolve_one(conn, symbol)
    params = SignalParams(**resolved["params"]).model_copy(
        update={"allow_long": True, "allow_short": True}
    )
    params_json = json.dumps(params.model_dump())

    bars = ohlc.load_ohlc(conn, symbol)
    if len(bars) < MIN_BARS:
        raise ValueError(f"{symbol}: only {len(bars)} bars — need >= {MIN_BARS} to run")

    run_id = repo.create_run(conn, "single", symbol, params_json, ENGINE_VERSION)
    try:
        fr = _full_result(bars, params)
        result, m, state = fr["result"], fr["metrics"], fr["state"]

        conn.execute("BEGIN")
        repo.wipe_symbol(conn, symbol)
        repo.insert_events(conn, run_id, symbol, result.trades)
        repo.upsert_symbol_stats(conn, run_id, symbol, params_json, state, m,
                                 strategy_id=resolved["id"])
        repo.insert_chart(conn, run_id, symbol, fr["payload"])
        repo.finish_run(conn, run_id, "succeeded", 1, len(result.trades))
        conn.execute("COMMIT")
    except Exception as exc:  # noqa: BLE001
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        repo.finish_run(conn, run_id, "failed", 0, 0, str(exc)[:300])
        raise

    return get_timing(conn, symbol)


# ---- read ----

def _markers(trades: list[dict]) -> list[dict]:
    out: list[dict] = []
    for t in trades:
        out.append({"time": t["entry_date"], "side": t["direction"], "kind": "entry",
                    "label": f"{t['direction']} entry"})
        if t["exit_date"]:
            out.append({"time": t["exit_date"], "side": t["direction"], "kind": "exit",
                        "label": t["exit_reason"] or "exit"})
    return out


def get_timing(conn: sqlite3.Connection, symbol: str) -> dict:
    symbol = ohlc.normalize_symbol(symbol)
    run = repo.latest_run_for_symbol(conn, symbol)
    if run is None:
        return {"status": "not_computed", "symbol": symbol}

    bars = ohlc.load_ohlc(conn, symbol)
    events = repo.get_events(conn, symbol, run["run_id"])
    stats = repo.get_symbol_stats(conn, symbol, run["run_id"]) or {}
    chart = repo.get_chart(conn, symbol, run["run_id"]) or {}

    newest = ohlc.latest_price_date(conn, symbol)
    run_through = bars[-1]["date"] if bars else None
    # a fresh price bar exists that the stored run did not see
    stale = bool(newest and chart.get("overlays", {}).get("dates")
                 and newest > chart["overlays"]["dates"][-1])

    return {
        "status": "ok",
        "symbol": symbol,
        "computed_at": run["finished_at"],
        "engine_version": run["engine_version"],
        "params": json.loads(run["params_json"]),
        "stale": stale,
        "newest_price_date": newest,
        "run_through_date": run_through,
        "bars": [{"time": b["date"], "open": b["o"], "high": b["h"], "low": b["l"],
                  "close": b["c"], "volume": b["v"]} for b in bars],
        "chart_cached": bool(chart),  # false after a universe (Trend) run — press Run for overlays
        "run_scope": run["scope"],
        "overlays": chart.get("overlays", {}),
        "key_levels": chart.get("key_levels", []),
        "equity": chart.get("equity", {}),
        "daily": chart.get("daily", []),
        "markers": _markers(events),
        "trades": events,
        "state": {
            "state": stats.get("state"), "state_since": stats.get("state_since"),
            "entry_price": stats.get("entry_price"), "last_close": stats.get("last_close"),
            "unrealized_pct": stats.get("unrealized_pct"), "current_stop": stats.get("current_stop"),
        },
        "metrics": json.loads(stats["metrics_json"]) if stats.get("metrics_json") else {},
    }


# ---- Trend: whole-universe run + board ----

_CHUNK = 25  # symbols between progress ticks / cancel checks


def _universe_targets(conn: sqlite3.Connection) -> list[str]:
    active = [r["symbol"] for r in conn.execute(
        "SELECT symbol FROM assets WHERE active = 1 ORDER BY symbol"
    )]
    crypto = [r["symbol"] for r in conn.execute(
        "SELECT symbol FROM crypto_assets WHERE active = 1"
    )] or ["BTC/USD", "ETH/USD"]
    seen: set[str] = set()
    out: list[str] = []
    for s in [*active, *crypto, *TREND_WATCHLIST]:
        s = ohlc.normalize_symbol(s)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def run_universe(conn: sqlite3.Connection, run_id: int, mode: str = "incremental") -> None:
    """`run_id` is the fetch_runs row driving the progress bar. A companion
    `signal_runs` row is the domain record the board reads."""
    # Resolve one strategy -> params per symbol from the registry (migration
    # 0014). Direction is forced two-sided regardless of the strategy so the
    # board always shows every short setup.
    resolved = repo.resolve_symbol_params(conn)
    default = repo.default_strategy(conn)
    targets = _universe_targets(conn)
    fetch_runs.set_planned(conn, run_id, len(targets))

    sig_run_id = repo.create_run(
        conn, "universe", None,
        json.dumps({"resolver": "signal_strategies per-symbol"}), ENGINE_VERSION,
    )
    param_cache: dict[str, tuple[SignalParams, str]] = {}

    def resolve(symbol: str) -> tuple[int, SignalParams, str]:
        res = resolved.get(symbol) or {"strategy_id": default["id"], "params": default["params"]}
        key = res["strategy_key"] if "strategy_key" in res else str(res["strategy_id"])
        if key not in param_cache:
            p = SignalParams(**res["params"]).model_copy(
                update={"allow_long": True, "allow_short": True}
            )
            param_cache[key] = (p, json.dumps(p.model_dump()))
        p, pj = param_cache[key]
        return res["strategy_id"], p, pj

    total_events = 0
    done = 0
    try:
        for i in range(0, len(targets), _CHUNK):
            fetch_runs.raise_if_cancelled(run_id)
            for symbol in targets[i:i + _CHUNK]:
                fetch_runs.start_target(conn, run_id, symbol)
                t0 = time.monotonic()
                bars = ohlc.load_ohlc(conn, symbol)
                if len(bars) < MIN_BARS:
                    fetch_runs.finish_target(conn, run_id, symbol, status="skipped",
                                             duration_ms=int((time.monotonic() - t0) * 1000))
                    done += 1
                    continue
                strategy_id, params, params_json = resolve(symbol)
                result = engine.run(bars, params)
                m = metrics.summarise(result.trades, result.daily, bars)
                state = _board_state(bars, result.trades, result.overlays)
                conn.execute("BEGIN")
                repo.wipe_symbol(conn, symbol)
                repo.insert_events(conn, sig_run_id, symbol, result.trades)
                repo.upsert_symbol_stats(conn, sig_run_id, symbol, params_json, state, m,
                                         strategy_id=strategy_id)
                conn.execute("COMMIT")
                total_events += len(result.trades)
                done += 1
                fetch_runs.finish_target(conn, run_id, symbol, status="ok",
                                         rows=len(result.trades),
                                         duration_ms=int((time.monotonic() - t0) * 1000))
        repo.finish_run(conn, sig_run_id, "succeeded", done, total_events)
    except Exception as exc:  # noqa: BLE001
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        repo.finish_run(conn, sig_run_id, "failed", done, total_events, str(exc)[:300])
        raise


def _board_entry(row: dict) -> dict:
    return {
        "symbol": row["symbol"],
        "state": row["state"],
        "state_since": row["state_since"],
        "entry_price": row["entry_price"],
        "last_close": row["last_close"],
        "unrealized_pct": row["unrealized_pct"],
        "current_stop": row["current_stop"],
    }


def _empty_entry(symbol: str) -> dict:
    return {"symbol": symbol, "state": None, "state_since": None, "entry_price": None,
            "last_close": None, "unrealized_pct": None, "current_stop": None}


def get_board(conn: sqlite3.Connection) -> dict:
    run = repo.latest_universe_run(conn)
    watch = repo.stats_for_symbols(conn, [ohlc.normalize_symbol(s) for s in TREND_WATCHLIST])
    watchlist = [
        {
            "title": title,
            "rows": [
                _board_entry(watch[s]) if s in watch else _empty_entry(s)
                for s in (ohlc.normalize_symbol(x) for x in syms)
            ],
        }
        for title, syms in TREND_WATCHLIST_SECTIONS
    ]
    strategies = repo.list_strategies(conn)
    if run is None:
        return {"status": "not_computed", "watchlist": watchlist, "strategies": strategies,
                "long": [], "short": [], "flat": []}

    rows = [_board_entry(r) for r in repo.board_rows(conn, run["run_id"])]
    buckets: dict[str, list[dict]] = {"long": [], "short": [], "flat": []}
    for r in rows:
        buckets.get(r["state"], buckets["flat"]).append(r)
    for k in buckets:
        buckets[k].sort(key=lambda r: (r["state_since"] or ""), reverse=True)
    return {
        "status": "ok",
        "computed_at": run["finished_at"],
        "engine_version": run["engine_version"],
        "counts": {k: len(v) for k, v in buckets.items()},
        "long": buckets["long"],
        "short": buckets["short"],
        "flat": buckets["flat"],
        "watchlist": watchlist,
        "strategies": strategies,
    }
