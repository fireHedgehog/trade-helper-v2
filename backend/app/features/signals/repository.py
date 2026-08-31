"""SQL for the signal_* tables. No engine logic here."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- config (single active preset) ----

def get_config(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT id, name, params_json, updated_at FROM signal_config "
        "WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("no active signal_config row (migration 0012 seeds one)")
    return {"id": row["id"], "name": row["name"],
            "params": json.loads(row["params_json"]), "updated_at": row["updated_at"]}


def save_config(conn: sqlite3.Connection, params: dict, name: str | None) -> None:
    cur = get_config(conn)
    conn.execute(
        "UPDATE signal_config SET params_json = ?, name = ?, updated_at = ? WHERE id = ?",
        (json.dumps(params), name or cur["name"], _now(), cur["id"]),
    )


# ---- strategy registry (migration 0014) ----

def _strategy_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["params"] = json.loads(d.pop("params_json"))
    d["is_default"] = bool(d["is_default"])
    return d


def list_strategies(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM assets a        WHERE a.strategy_id = s.id)
             + (SELECT COUNT(*) FROM crypto_assets c WHERE c.strategy_id = s.id) AS assigned_count
          FROM signal_strategies s
         ORDER BY s.is_default DESC, s.id
        """
    ).fetchall()
    return [_strategy_row(r) for r in rows]


def get_strategy(conn: sqlite3.Connection, strategy_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM signal_strategies WHERE id = ?", (strategy_id,)).fetchone()
    return _strategy_row(r) if r else None


def default_strategy(conn: sqlite3.Connection) -> dict:
    r = conn.execute(
        "SELECT * FROM signal_strategies WHERE is_default = 1 ORDER BY id LIMIT 1"
    ).fetchone() or conn.execute("SELECT * FROM signal_strategies ORDER BY id LIMIT 1").fetchone()
    if r is None:
        raise RuntimeError("no signal_strategies rows (migration 0014 seeds two)")
    return _strategy_row(r)


def strategy_symbols(conn: sqlite3.Connection, strategy_id: int) -> list[str]:
    crypto = [row["symbol"] for row in conn.execute(
        "SELECT symbol FROM crypto_assets WHERE strategy_id = ? ORDER BY symbol", (strategy_id,))]
    equity = [row["symbol"] for row in conn.execute(
        "SELECT symbol FROM assets WHERE strategy_id = ? ORDER BY symbol", (strategy_id,))]
    return [*crypto, *equity]


def assign_strategy(conn: sqlite3.Connection, strategy_id: int, symbols: list[str]) -> int:
    if not symbols:
        return 0
    ph = ",".join("?" for _ in symbols)
    conn.execute("BEGIN")
    try:
        n = conn.execute(
            f"UPDATE assets SET strategy_id = ? WHERE symbol IN ({ph})",
            (strategy_id, *symbols),
        ).rowcount
        n += conn.execute(
            f"UPDATE crypto_assets SET strategy_id = ? WHERE symbol IN ({ph})",
            (strategy_id, *symbols),
        ).rowcount
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return n


def resolve_one(conn: sqlite3.Connection, symbol: str) -> dict:
    """The strategy a single symbol currently resolves to (falls back to default)."""
    row = conn.execute(
        "SELECT strategy_id FROM assets WHERE symbol = ? "
        "UNION ALL SELECT strategy_id FROM crypto_assets WHERE symbol = ?",
        (symbol, symbol),
    ).fetchone()
    sid = row["strategy_id"] if row and row["strategy_id"] is not None else None
    return (get_strategy(conn, sid) if sid else None) or default_strategy(conn)


def resolve_symbol_params(conn: sqlite3.Connection) -> dict[str, dict]:
    """symbol -> {strategy_id, strategy_key, params} for every asset + crypto row.
    A row with no strategy_id (e.g. a freshly synced asset) falls back to the
    default strategy."""
    strategies = {s["id"]: s for s in list_strategies(conn)}
    default = strategies.get(next((sid for sid, s in strategies.items() if s["is_default"]), None)) \
        or default_strategy(conn)
    out: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT symbol, strategy_id FROM assets WHERE active = 1 "
        "UNION ALL SELECT symbol, strategy_id FROM crypto_assets WHERE active = 1"
    ):
        s = strategies.get(row["strategy_id"]) or default
        out[row["symbol"]] = {
            "strategy_id": s["id"], "strategy_key": s["key"], "params": s["params"],
        }
    return out


# ---- runs ----

def create_run(conn: sqlite3.Connection, scope: str, symbol: str | None,
               params_json: str, engine_version: str,
               profile: str | None = None, directions: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO signal_runs (scope, symbol, params_json, engine_version, status, "
        "started_at, profile, directions) VALUES (?,?,?,?,'running',?,?,?)",
        (scope, symbol, params_json, engine_version, _now(), profile, directions),
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, status: str,
               n_symbols: int, n_events: int, error: str | None = None) -> None:
    conn.execute(
        "UPDATE signal_runs SET status = ?, finished_at = ?, n_symbols = ?, n_events = ?, error = ? "
        "WHERE run_id = ?",
        (status, _now(), n_symbols, n_events, error, run_id),
    )


def latest_run_for_symbol(conn: sqlite3.Connection, symbol: str) -> dict | None:
    """The run that currently owns this symbol's rows — `wipe_symbol` means a
    symbol has at most one `signal_symbol_stats` row at a time, written by
    either a single Timing run or the universe (Trend) run, whichever ran
    last for it."""
    row = conn.execute(
        """
        SELECT r.* FROM signal_runs r
          JOIN signal_symbol_stats s ON s.run_id = r.run_id
         WHERE s.symbol = ? AND r.status = 'succeeded'
         ORDER BY r.run_id DESC LIMIT 1
        """,
        (symbol,),
    ).fetchone()
    return dict(row) if row else None


def latest_universe_run(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM signal_runs WHERE scope = 'universe' AND status = 'succeeded' "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def board_rows(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT symbol, state, state_since, entry_price, last_close, last_date,
               unrealized_pct, current_stop
          FROM signal_symbol_stats WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def stats_for_symbols(conn: sqlite3.Connection, symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    ph = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"""
        SELECT s.symbol, s.state, s.state_since, s.entry_price, s.last_close,
               s.unrealized_pct, s.current_stop
          FROM signal_symbol_stats s
         WHERE s.symbol IN ({ph})
        """,
        symbols,
    ).fetchall()
    return {r["symbol"]: dict(r) for r in rows}


# ---- per-symbol wipe + write (full recompute, docs/01-data-model.md) ----

def wipe_symbol(conn: sqlite3.Connection, symbol: str) -> None:
    for tbl in ("signal_events", "signal_symbol_stats", "signal_chart"):
        conn.execute(f"DELETE FROM {tbl} WHERE symbol = ?", (symbol,))


def insert_events(conn: sqlite3.Connection, run_id: int, symbol: str, trades: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO signal_events (run_id, symbol, direction, entry_date, entry_price,
            exit_date, exit_price, exit_reason, bars_held, return_pct, return_r,
            mae_atr, mfe_atr, initial_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (run_id, symbol, t["direction"], t["entry_date"], t["entry_price"],
             t["exit_date"], t["exit_price"], t["exit_reason"], t["bars_held"],
             t["return_pct"], t["return_r"], t["mae_atr"], t["mfe_atr"], t["initial_stop"])
            for t in trades
        ],
    )


def upsert_symbol_stats(conn: sqlite3.Connection, run_id: int, symbol: str, params_json: str,
                        state: dict, metrics: dict, profile: str | None = None,
                        strategy_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO signal_symbol_stats (run_id, symbol, params_json, state, state_since,
            entry_price, last_close, last_date, unrealized_pct, current_stop, metrics_json,
            updated_at, profile, strategy_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id, symbol) DO UPDATE SET
            params_json=excluded.params_json, state=excluded.state, state_since=excluded.state_since,
            entry_price=excluded.entry_price, last_close=excluded.last_close, last_date=excluded.last_date,
            unrealized_pct=excluded.unrealized_pct, current_stop=excluded.current_stop,
            metrics_json=excluded.metrics_json, updated_at=excluded.updated_at, profile=excluded.profile,
            strategy_id=excluded.strategy_id
        """,
        (run_id, symbol, params_json, state["state"], state["state_since"],
         state["entry_price"], state["last_close"], state["last_date"],
         state["unrealized_pct"], state["current_stop"], json.dumps(metrics), _now(), profile,
         strategy_id),
    )


def insert_chart(conn: sqlite3.Connection, run_id: int, symbol: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO signal_chart (run_id, symbol, payload_json) VALUES (?,?,?) "
        "ON CONFLICT(run_id, symbol) DO UPDATE SET payload_json = excluded.payload_json",
        (run_id, symbol, json.dumps(payload)),
    )


def get_events(conn: sqlite3.Connection, symbol: str, run_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT direction, entry_date, entry_price, exit_date, exit_price, exit_reason, "
        "bars_held, return_pct, return_r, mae_atr, mfe_atr, initial_stop "
        "FROM signal_events WHERE symbol = ? AND run_id = ? ORDER BY entry_date",
        (symbol, run_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_symbol_stats(conn: sqlite3.Connection, symbol: str, run_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM signal_symbol_stats WHERE symbol = ? AND run_id = ?", (symbol, run_id)
    ).fetchone()
    return dict(row) if row else None


def get_chart(conn: sqlite3.Connection, symbol: str, run_id: int) -> dict | None:
    row = conn.execute(
        "SELECT payload_json FROM signal_chart WHERE symbol = ? AND run_id = ?", (symbol, run_id)
    ).fetchone()
    return json.loads(row["payload_json"]) if row else None
