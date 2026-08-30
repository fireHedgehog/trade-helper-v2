"""Data access for the ``credentials`` table. Metadata only — no secrets."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_COLUMNS = (
    "provider_key, credential_name, environment_variable, configured, "
    "verification_status, last_verified_at, last_verification_detail, "
    "created_at, updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(conn: sqlite3.Connection, provider_key: str) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {_COLUMNS} FROM credentials WHERE provider_key = ?",
        (provider_key,),
    ).fetchone()


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT {_COLUMNS} FROM credentials ORDER BY provider_key"
    ).fetchall()


def mark_configured(conn: sqlite3.Connection, provider_key: str) -> None:
    """A secret was (re)written: mark configured, reset verification."""
    conn.execute(
        """
        UPDATE credentials
           SET configured = 1,
               verification_status = 'unverified',
               last_verified_at = NULL,
               last_verification_detail = NULL,
               updated_at = ?
         WHERE provider_key = ?
        """,
        (_now(), provider_key),
    )


def clear(conn: sqlite3.Connection, provider_key: str) -> None:
    conn.execute(
        """
        UPDATE credentials
           SET configured = 0,
               verification_status = 'unverified',
               last_verified_at = NULL,
               last_verification_detail = NULL,
               updated_at = ?
         WHERE provider_key = ?
        """,
        (_now(), provider_key),
    )


def record_verification(
    conn: sqlite3.Connection,
    provider_key: str,
    status: str,
    detail: str,
) -> None:
    conn.execute(
        """
        UPDATE credentials
           SET verification_status = ?,
               last_verified_at = ?,
               last_verification_detail = ?,
               updated_at = ?
         WHERE provider_key = ?
        """,
        (status, _now(), detail, _now(), provider_key),
    )
