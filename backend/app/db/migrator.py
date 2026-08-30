"""Minimal forward-only migration runner.

Applies every ``schema/migrations/NNNN_*.sql`` file that has not been applied
yet, in filename order. Each file's script plus its tracking-row insert are
committed together, so a failed migration leaves nothing behind. Applied
versions are recorded in ``schema_migrations``.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


def _migration_files(schema_dir: Path) -> list[Path]:
    if not schema_dir.is_dir():
        raise FileNotFoundError(f"Schema directory not found: {schema_dir}")
    return sorted(p for p in schema_dir.glob("*.sql") if p.is_file())


def _connect(db_path: Path) -> sqlite3.Connection:
    # Default (deferred) isolation so we can commit the script + tracking row
    # as one unit. executescript() issues a COMMIT before it runs but not
    # after, so the trailing insert joins the same open transaction.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations() -> list[str]:
    """Apply pending migrations. Returns the list of versions applied now."""
    settings = get_settings()
    files = _migration_files(settings.schema_dir)
    db_path = settings.resolved_database_path()

    applied_now: list[str] = []
    conn = _connect(db_path)
    try:
        conn.execute(_TRACKING_TABLE)
        conn.commit()
        already = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}

        for path in files:
            version = path.stem  # e.g. "0001_init"
            if version in already:
                continue
            logger.info("Applying migration %s", version)
            try:
                conn.executescript(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Migration %s failed; rolled back", version)
                raise
            applied_now.append(version)
    finally:
        conn.close()

    if applied_now:
        logger.info("Applied %d migration(s): %s", len(applied_now), ", ".join(applied_now))
    else:
        logger.info("Database schema is up to date")
    return applied_now
