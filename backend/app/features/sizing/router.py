"""Explicit portfolio simulation; no data fetch or macro AI side effects."""
import sqlite3
from fastapi import APIRouter, Depends
from app.db.connection import db_dependency
from app.features.data_management import worker
from app.features.sizing import service
from app.features.sizing.params import SizingRequest

router=APIRouter(prefix='/api/sizing',tags=['sizing'])

@router.post('/run')
def run(body:SizingRequest):
    run_id,deduped=worker.submit('portfolio_simulation',scope_arg=body.model_dump_json())
    return {'run_id':run_id,'deduped':deduped}

@router.get('/latest')
def latest(conn:sqlite3.Connection=Depends(db_dependency)):
    return service.latest(conn)
