"""HTTP routes for the Data Management page.

    POST   /api/data/runs                          start a fetch
    GET    /api/data/runs?limit=                   recent runs (history)
    GET    /api/data/runs/{id}                     one run (progress polling)
    GET    /api/data/runs/{id}/items               per-target results
    POST   /api/data/runs/{id}/cancel             request cancellation

    GET    /api/data/assets                        paginated assets + bar stats
    GET    /api/data/assets/{symbol}               one asset + memberships
    GET    /api/data/assets/{symbol}/bars          paginated price_bars

    GET    /api/data/macro                         macro catalog + obs stats
    GET    /api/data/macro/{series_id}/observations
    GET    /api/data/crypto                        crypto assets + bar stats
    GET    /api/data/crypto/bars?symbol=BTC/USD
    GET    /api/data/commodities                   commodity catalog + stats
    GET    /api/data/commodities/{instrument}/prices
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.connection import db_dependency
from app.features.data_management import repository as repo
from app.features.data_management import runs, worker
from app.features.data_management.schemas import RunStatus, StartRunRequest, StartRunResponse

router = APIRouter(prefix="/api/data", tags=["data-management"])


# ---- runs ----

@router.post("/runs", response_model=StartRunResponse)
def start_run(body: StartRunRequest):
    if body.scope == "single" and not body.scope_arg:
        raise HTTPException(400, "scope=single requires scope_arg (a symbol)")
    try:
        run_id, deduped = worker.submit(body.kind, body.mode, body.scope, body.scope_arg)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))
    return StartRunResponse(run_id=run_id, deduped=deduped)


@router.get("/runs", response_model=list[RunStatus])
def recent_runs(limit: int = Query(25, ge=1, le=100),
                conn: sqlite3.Connection = Depends(db_dependency)):
    return [RunStatus(**r, queue_depth=0) for r in runs.list_runs(conn, limit)]


@router.get("/runs/active", response_model=list[RunStatus])
def active_runs(conn: sqlite3.Connection = Depends(db_dependency)):
    """Everything queued or running right now — used to re-attach after a page reload."""
    return [RunStatus(**r, queue_depth=worker.queue_depth()) for r in runs.list_active(conn)]


@router.get("/runs/{run_id}", response_model=RunStatus)
def run_status(run_id: int, conn: sqlite3.Connection = Depends(db_dependency)):
    row = runs.get_run(conn, run_id)
    if not row:
        raise HTTPException(404, f"No run {run_id}")
    return RunStatus(**row, queue_depth=worker.queue_depth())


@router.get("/runs/{run_id}/items")
def run_items(run_id: int, conn: sqlite3.Connection = Depends(db_dependency)):
    return runs.list_run_items(conn, run_id)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, conn: sqlite3.Connection = Depends(db_dependency)):
    row = runs.get_run(conn, run_id)
    if not row:
        raise HTTPException(404, f"No run {run_id}")
    if row["status"] == "running":
        runs.request_cancel(run_id)
    return {"ok": True, "status": row["status"]}


# ---- browse ----

@router.get("/assets")
def assets(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    active_only: bool = True,
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_assets(conn, q, page, page_size, active_only)


@router.get("/assets/{symbol}")
def asset_detail(symbol: str, conn: sqlite3.Connection = Depends(db_dependency)):
    data = repo.get_asset(conn, symbol.upper())
    if not data:
        raise HTTPException(404, f"No asset {symbol}")
    return data


@router.get("/assets/{symbol}/bars")
def asset_bars(
    symbol: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_price_bars(conn, symbol.upper(), page, page_size)


@router.get("/memberships")
def memberships(conn: sqlite3.Connection = Depends(db_dependency)):
    return repo.list_memberships(conn)


@router.get("/memberships/{group_key}/members")
def membership_members(
    group_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_group_members(conn, group_key.upper(), page, page_size)


@router.get("/options")
def options(conn: sqlite3.Connection = Depends(db_dependency)):
    return repo.list_option_stats(conn)


@router.get("/macro")
def macro(category: str | None = None, conn: sqlite3.Connection = Depends(db_dependency)):
    return repo.list_macro(conn, category)


@router.get("/macro/{series_id}/observations")
def macro_observations(
    series_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_macro_observations(conn, series_id, page, page_size)


@router.get("/crypto")
def crypto(conn: sqlite3.Connection = Depends(db_dependency)):
    return repo.list_crypto(conn)


@router.get("/crypto/bars")
def crypto_bars(
    symbol: str = Query(..., description="e.g. BTC/USD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_crypto_bars(conn, symbol.upper(), page, page_size)


@router.get("/commodities")
def commodities(conn: sqlite3.Connection = Depends(db_dependency)):
    return repo.list_commodities(conn)


@router.get("/commodities/{instrument}/prices")
def commodity_prices(
    instrument: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
    conn: sqlite3.Connection = Depends(db_dependency),
):
    return repo.list_commodity_prices(conn, instrument.upper(), page, page_size)
