"""SQLite connection helper.

Single-operator, local-first app: one file, short-lived connections, foreign
keys on, rows returned as mappings.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import get_settings


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    db_path = settings.resolved_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may create a sync dependency's
    # connection in a threadpool thread and use it from the event-loop thread
    # for an async route. Each request still gets its own connection and never
    # shares it concurrently, so this is safe here.
    conn = sqlite3.connect(
        db_path, isolation_level=None, check_same_thread=False
    )  # autocommit; we manage txns explicitly
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # A background job (e.g. the whole-universe signal run) writes from a
    # worker thread while HTTP requests read on the loop thread — wait out a
    # brief lock instead of failing.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a connection, always closed afterwards."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Yield a connection wrapped in a single transaction."""
    conn = _connect()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


# FastAPI dependency.
def db_dependency() -> Iterator[sqlite3.Connection]:
    with get_connection() as conn:
        yield conn
