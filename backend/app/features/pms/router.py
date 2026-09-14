"""Explicit PM run/asset selection; reads never compute or select another PM."""
import json
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.db.connection import db_dependency
from . import service, repository, assessment

router=APIRouter(prefix='/api/pms',tags=['pms'])


class RunRequest(BaseModel):
    symbols: list[str] | None = Field(default=None,min_length=1,max_length=2000)


@router.post('/run')
def run(body: RunRequest):
    from app.features.data_management import worker
    run_id,deduped=worker.submit('pm_universe',scope_arg=json.dumps(body.symbols) if body.symbols else None)
    return {'run_id':run_id,'deduped':deduped}


@router.get('/choices/{symbol:path}')
def choices(symbol: str, run_id: int | None = None, conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.choices(conn,symbol,run_id)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get('/timing/{symbol:path}')
def timing(symbol: str,run_id: int,key: str,version: str,conn: sqlite3.Connection=Depends(db_dependency)):
    try: return service.timing(conn,run_id,symbol,key,version)
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
