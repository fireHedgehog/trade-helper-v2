"""Signal engine API (Trend / Timing pages).

    GET  /api/signals/config                     vestigial single preset (fallback)
    PUT  /api/signals/config                     (kept; the Timing page no longer calls it)
    POST /api/signals/preview {symbol, params}   run one symbol live, persist NOTHING
    POST /api/signals/run {symbol}               run + persist (used by the board / links)
    GET  /api/signals/timing/{symbol}            last cached run for the symbol
    POST /api/signals/run-universe               background whole-universe run (Trend)
    GET  /api/signals/board                      the last universe run as 3 state tables

    GET  /api/signals/strategies                 the strategy registry (migration 0014)
    GET  /api/signals/strategies/{id}            one strategy + its assigned symbols
    POST /api/signals/strategies/{id}/assign     point a symbol selection at a strategy
    GET  /api/signals/strategies/resolve/{sym}   the strategy a symbol resolves to

Long / short is a **view filter** on the Timing page and never a strategy
filter — the board computes both sides for every symbol.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.connection import db_dependency
from app.features.signals import service
from app.features.signals.params import SignalParams

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SaveConfigRequest(BaseModel):
    name: str | None = None
    params: SignalParams


class RunRequest(BaseModel):
    symbol: str


class PreviewRequest(BaseModel):
    symbol: str
    params: SignalParams


class AssignRequest(BaseModel):
    symbols: list[str]


@router.get("/config")
def get_config(conn: sqlite3.Connection = Depends(db_dependency)):
    return service.get_config(conn)


@router.put("/config")
def put_config(body: SaveConfigRequest, conn: sqlite3.Connection = Depends(db_dependency)):
    return service.save_config(conn, body.params, body.name)


@router.post("/preview")
def preview(body: PreviewRequest, conn: sqlite3.Connection = Depends(db_dependency)):
    try:
        return service.preview(conn, body.symbol, body.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run")
def run(body: RunRequest, conn: sqlite3.Connection = Depends(db_dependency)):
    try:
        return service.run_for_symbol(conn, body.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/strategies")
def strategies(conn: sqlite3.Connection = Depends(db_dependency)):
    return service.list_strategies(conn)


@router.get("/strategies/resolve/{symbol:path}")
def resolve_strategy(symbol: str, conn: sqlite3.Connection = Depends(db_dependency)):
    return service.resolved_strategy(conn, symbol)


@router.get("/strategies/{strategy_id}")
def strategy_detail(strategy_id: int, conn: sqlite3.Connection = Depends(db_dependency)):
    try:
        return service.strategy_detail(conn, strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/strategies/{strategy_id}/assign")
def assign_strategy(
    strategy_id: int, body: AssignRequest, conn: sqlite3.Connection = Depends(db_dependency)
):
    try:
        return service.assign_strategy(conn, strategy_id, body.symbols)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/timing/{symbol:path}")
def timing(symbol: str, conn: sqlite3.Connection = Depends(db_dependency)):
    return service.get_timing(conn, symbol)


@router.post("/run-universe")
def run_universe():
    """Kick a background run over every active symbol + the cross-asset trio +
    the watchlist. Poll progress via `GET /api/data/runs/{run_id}` (same
    infrastructure as the Data-management fetches)."""
    from app.features.data_management import worker

    run_id, deduped = worker.submit("signal_universe")
    return {"run_id": run_id, "deduped": deduped}


@router.get("/board")
def board(charts: bool = False, conn: sqlite3.Connection = Depends(db_dependency)):
    # charts=1 attaches per-watchlist-row mini-chart bars + trade markers (~200 KB);
    # the Trend page requests it only in "graph mode".
    return service.get_board(conn, charts=charts)
