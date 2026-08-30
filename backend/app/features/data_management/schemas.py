"""Request/response models for the Data Management API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FetchKind = Literal[
    "asset_catalog", "asset_prices", "crypto_bars", "commodity_prices", "macro",
    "memberships", "option_snapshots", "signal_universe",
]


class StartRunRequest(BaseModel):
    kind: FetchKind
    mode: Literal["incremental", "full"] = "incremental"
    scope: Literal["all", "watchlist", "single"] = "all"
    scope_arg: str | None = None


class StartRunResponse(BaseModel):
    run_id: int
    deduped: bool = False  # true = attached to an already-active run of this kind


class RunStatus(BaseModel):
    id: int
    kind: str
    mode: str
    scope: str
    scope_arg: str | None = None
    status: str
    planned_targets: int
    completed_targets: int
    failed_targets: int
    rows_written: int
    requests_made: int
    current_target: str | None = None
    started_at: str
    finished_at: str | None = None
    error_summary: str | None = None
    queue_depth: int = Field(default=0, description="jobs waiting behind this one")
