"""Signal engine API (Trend / Timing pages).

    GET  /api/signals/config              the active parameter set
    PUT  /api/signals/config              save the active parameter set
    POST /api/signals/run {symbol}        run one symbol, persist, return payload
    GET  /api/signals/timing/{symbol}     last cached run for the symbol
    POST /api/signals/run-universe        background whole-universe run (Trend)
    GET  /api/signals/board               the last universe run as 3 state tables

Long / short is a **view filter** on the Timing page (which markers / trades /
metrics to render) — it does not touch this API.
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


@router.get("/config")
def get_config(conn: sqlite3.Connection = Depends(db_dependency)):
    return service.get_config(conn)


@router.put("/config")
def put_config(body: SaveConfigRequest, conn: sqlite3.Connection = Depends(db_dependency)):
    return service.save_config(conn, body.params, body.name)


@router.post("/run")
def run(body: RunRequest, conn: sqlite3.Connection = Depends(db_dependency)):
    try:
        return service.run_for_symbol(conn, body.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def board(conn: sqlite3.Connection = Depends(db_dependency)):
    return service.get_board(conn)
