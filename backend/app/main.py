"""FastAPI application entry point.

Run from the backend/ folder:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.migrator import run_migrations
from app.features.data_management import worker as fetch_worker
from app.providers import loader as _provider_loader  # noqa: F401  (registers providers)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Database: %s", settings.resolved_database_path())
    run_migrations()
    fetch_worker.start_worker()
    try:
        yield
    finally:
        await fetch_worker.stop_worker()


app = FastAPI(title="Trade Helper API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Feature routers.
from app.features.credentials.router import router as credentials_router  # noqa: E402
from app.features.data_management.router import router as data_router  # noqa: E402
from app.features.macro.router import router as macro_router  # noqa: E402
from app.features.multisectional.router import router as multisectional_router  # noqa: E402
from app.features.signals.router import router as signals_router  # noqa: E402

app.include_router(credentials_router)
app.include_router(data_router)
app.include_router(macro_router)
app.include_router(multisectional_router)
app.include_router(signals_router)
