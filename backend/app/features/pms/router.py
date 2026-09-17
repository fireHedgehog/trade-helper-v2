"""Explicit PM run/asset selection; reads never compute or select another PM."""
import json
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.db.connection import db_dependency
from . import service, repository, assessment, registry, trend

router=APIRouter(prefix='/api/pms',tags=['pms'])


class RunRequest(BaseModel):
    family: str | None = None
    symbols: list[str] | None = Field(default=None,min_length=1,max_length=2000)


@router.post('/run')
def run(body: RunRequest):
    from app.features.data_management import worker
    if body.family:
        try: registry.get(body.family)
        except ValueError as exc: raise HTTPException(400, detail=str(exc)) from exc
    scope = {'family':body.family,'symbols':body.symbols} if body.family else body.symbols
    run_id,deduped=worker.submit('pm_universe',mode='full',scope_arg=json.dumps(scope) if scope else None)
    return {'run_id':run_id,'deduped':deduped}


@router.get('/strategies')
def strategies():
    return registry.catalog()


@router.get('/trend/{family}')
def trend_board(family: str,charts: bool=False,run_id: int | None=None,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return trend.board(conn,family,charts,run_id)
    except ValueError as exc: raise HTTPException(404,detail=str(exc)) from exc


@router.get('/choices/{symbol:path}')
def choices(symbol: str, run_id: int | None = None, family: str | None = None, conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.choices(conn,symbol,run_id,family)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get('/timing/{symbol:path}')
def timing(symbol: str,run_id: int,key: str,version: str,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.timing(conn,run_id,symbol,key,version)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get('/family-timing/{symbol:path}')
def family_timing(symbol: str,run_id: int,family: str,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.family_timing(conn,run_id,symbol,family)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get('/runs/{run_id}')
def get_run(run_id: int,conn: sqlite3.Connection=Depends(db_dependency)):
    result=repository.get_run(conn,run_id)
    if result is None: raise HTTPException(status_code=404,detail='PM run not found')
    return result


@router.get('/board')
def board(run_id: int | None=None,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.board(conn,run_id)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get('/assessment/{symbol:path}')
def assess(symbol: str,run_id: int | None=None,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return assessment.read(conn,symbol,run_id)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
