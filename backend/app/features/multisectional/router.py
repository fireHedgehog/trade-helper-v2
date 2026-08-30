"""Multisectional (cross-sectional ranking) API.

    GET  /api/multisectional/ranking            the last cached snapshot
                                                (+ a staleness hint). Fast.
    POST /api/multisectional/ranking/recompute  run the ~2 s computation over
                                                every active symbol and store
                                                a fresh snapshot.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.db.connection import db_dependency
from app.features.multisectional import ranking

router = APIRouter(prefix="/api/multisectional", tags=["multisectional"])


@router.get("/ranking")
def cross_sectional_ranking(conn: sqlite3.Connection = Depends(db_dependency)):
    """The last stored ranking — no recompute. Returns `status: not_computed`
    with `stale: true` if nothing has been computed yet."""
    return ranking.latest_ranking(conn)


@router.post("/ranking/recompute")
def recompute(conn: sqlite3.Connection = Depends(db_dependency)):
    """Compute from the current `price_bars` and store the snapshot."""
    return ranking.recompute_and_store(conn)
