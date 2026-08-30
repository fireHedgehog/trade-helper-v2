"""fetch_runs / fetch_run_items bookkeeping + cancellation flags.

Handlers call start_target / finish_target per symbol|series so a crash or
cancel loses at most the one in-flight target, and the progress bar (which
polls `get_run`) always reflects committed work.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_cancel_requested: set[int] = set()


class RunCancelled(Exception):
    """Raised by a handler when it sees its run was cancelled."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- lifecycle ----

ACTIVE_STATUSES = ("queued", "running")


def create_run(
    conn: sqlite3.Connection,
    kind: str,
    mode: str = "incremental",
    scope: str = "all",
    scope_arg: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO fetch_runs (kind, mode, scope, scope_arg, status, started_at)
        VALUES (?, ?, ?, ?, 'queued', ?)
        """,
        (kind, mode, scope, scope_arg, _now()),
    )
    return int(cur.lastrowid)


def mark_running(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE fetch_runs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
        (_now(), run_id),
    )


def active_run_for_kind(conn: sqlite3.Connection, kind: str) -> int | None:
    """The id of a queued/running run of this kind, if one exists (for dedup)."""
    row = conn.execute(
        "SELECT id FROM fetch_runs WHERE kind = ? AND status IN ('queued','running') "
        "ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return int(row["id"]) if row else None


def set_planned(conn: sqlite3.Connection, run_id: int, n: int) -> None:
    conn.execute("UPDATE fetch_runs SET planned_targets = ? WHERE id = ?", (n, run_id))


def start_target(conn: sqlite3.Connection, run_id: int, target: str) -> None:
    conn.execute("BEGIN")
    conn.execute("UPDATE fetch_runs SET current_target = ? WHERE id = ?", (target, run_id))
    conn.execute(
        """
        INSERT INTO fetch_run_items (run_id, target, status)
        VALUES (?, ?, 'pending')
        ON CONFLICT(run_id, target) DO UPDATE SET status = 'pending'
        """,
        (run_id, target),
    )
    conn.execute("COMMIT")


def finish_target(
    conn: sqlite3.Connection,
    run_id: int,
    target: str,
    *,
    status: str,
    rows: int = 0,
    requests: int = 0,
    coverage_start: str | None = None,
    coverage_end: str | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    conn.execute("BEGIN")
    conn.execute(
        """
        UPDATE fetch_run_items
           SET status = ?, rows_written = ?, requests_made = ?,
               coverage_start = ?, coverage_end = ?, duration_ms = ?, error = ?
         WHERE run_id = ? AND target = ?
        """,
        (status, rows, requests, coverage_start, coverage_end, duration_ms, error, run_id, target),
    )
    failed_inc = 1 if status == "error" else 0
    conn.execute(
        """
        UPDATE fetch_runs
           SET completed_targets = completed_targets + 1,
               failed_targets   = failed_targets + ?,
               rows_written     = rows_written + ?,
               requests_made    = requests_made + ?
         WHERE id = ?
        """,
        (failed_inc, rows, requests, run_id),
    )
    conn.execute("COMMIT")


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    error_summary: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE fetch_runs
           SET status = ?, finished_at = ?, current_target = NULL, error_summary = ?
         WHERE id = ?
        """,
        (status, _now(), error_summary, run_id),
    )
    _cancel_requested.discard(run_id)


# ---- cancellation ----

def request_cancel(run_id: int) -> None:
    _cancel_requested.add(run_id)


def is_cancelled(run_id: int) -> bool:
    return run_id in _cancel_requested


def raise_if_cancelled(run_id: int) -> None:
    if run_id in _cancel_requested:
        raise RunCancelled


# ---- reads ----

_RUN_COLS = (
    "id, kind, mode, scope, scope_arg, status, planned_targets, completed_targets, "
    "failed_targets, rows_written, requests_made, current_target, started_at, "
    "finished_at, error_summary"
)


def get_run(conn: sqlite3.Connection, run_id: int) -> dict | None:
    row = conn.execute(
        f"SELECT {_RUN_COLS} FROM fetch_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else None


def list_runs(conn: sqlite3.Connection, limit: int = 25) -> list[dict]:
    rows = conn.execute(
        f"SELECT {_RUN_COLS} FROM fetch_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_active(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        f"SELECT {_RUN_COLS} FROM fetch_runs WHERE status IN ('queued','running') ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def list_run_items(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT run_id, target, status, rows_written, requests_made,
               coverage_start, coverage_end, duration_ms, error
          FROM fetch_run_items
         WHERE run_id = ?
         ORDER BY (status = 'error') DESC, target
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]
