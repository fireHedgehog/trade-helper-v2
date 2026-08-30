"""Macro page API.

    GET  /api/macro/overview                     category grid + naive composite
    GET  /api/macro/ai-regime/models             catalogue rows (+ ?check=1)
    GET  /api/macro/ai-regime/models/account     real chat model ids on the key
    GET  /api/macro/ai-regime/budgets            small / medium / large presets
    POST /api/macro/ai-regime/run                run the adversarial voting agent
    GET  /api/macro/ai-regime/latest             today's cached run (or the last one)
    GET  /api/macro/ai-regime/history            recent runs (for the history strip)
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import db_dependency
from app.features.macro import overview as macro_overview
from app.features.macro.ai_regime import model_catalog as mc
from app.features.macro.ai_regime import repository as ai_repo
from app.features.macro.ai_regime import runner as ai_runner

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/overview")
def overview(conn: sqlite3.Connection = Depends(db_dependency)):
    return macro_overview.build_overview(conn)


@router.get("/ai-regime/models")
async def list_models(check: bool = Query(False, description="also check the OpenAI account")):
    models = mc.load_models()
    account: set[str] = set(await mc.account_chat_models()) if check else set()
    rows = []
    for m in models:
        d = asdict(m)
        d["available_on_account"] = (m.id in account) if check else None
        rows.append(d)
    return {"models": rows, "default": mc.default_model_id(), "checked": check}


@router.get("/ai-regime/models/account")
async def account_models():
    return {"models": await mc.account_chat_models()}


@router.get("/ai-regime/budgets")
def list_budgets():
    return [asdict(b) for b in mc.load_budgets()]


class RunRegimeRequest(BaseModel):
    model: str | None = None
    budget: str = "medium"
    force: bool = False


@router.post("/ai-regime/run")
async def run_regime(
    body: RunRegimeRequest, conn: sqlite3.Connection = Depends(db_dependency)
):
    """Blocking — makes 4–9 OpenAI calls (~15–60 s). Cached per trading date;
    `force=true` re-runs and replaces today's."""
    try:
        return await ai_runner.run(
            conn, model=body.model, budget_key=body.budget, force=body.force
        )
    except ai_runner.RegimeRunError as exc:
        raise HTTPException(400, str(exc))


@router.get("/ai-regime/latest")
def latest_regime(conn: sqlite3.Connection = Depends(db_dependency)):
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    run = ai_repo.get_by_date(conn, today) or ai_repo.get_latest(conn)
    return ai_repo.full(conn, run) or {"run": None}


@router.get("/ai-regime/history")
def regime_history(
    limit: int = Query(30, ge=1, le=120), conn: sqlite3.Connection = Depends(db_dependency)
):
    return ai_repo.history(conn, limit)
