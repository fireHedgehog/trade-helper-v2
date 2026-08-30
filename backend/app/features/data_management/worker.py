"""Single background fetch worker.

One asyncio task drains a queue, one job at a time (no concurrency — matches
the pacing policy). A job maps to a `fetch_runs` row; the handler updates its
counters per target so the progress bar (which polls the run row) always
shows committed work. Cancellation is checked between targets.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.features.data_management import (
    catalog, commodities, crypto, macro, memberships, options, prices, runs,
)

logger = logging.getLogger(__name__)

VALID_KINDS = {
    "asset_catalog", "asset_prices", "crypto_bars", "commodity_prices", "macro",
    "memberships", "option_snapshots", "signal_universe",
}


@dataclass
class Job:
    run_id: int
    kind: str
    mode: str
    scope: str
    scope_arg: str | None


_queue: asyncio.Queue[Job] | None = None
_task: asyncio.Task | None = None


def _reconcile_orphaned_runs() -> None:
    """A single-process worker owns every run. Any row still `queued`/`running`
    at startup was orphaned when the previous process stopped — no worker is
    driving it, so mark it failed and let the UI move on. Per-target work that
    already committed stays; a re-submit resumes from there (incremental)."""
    with get_connection() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM fetch_runs WHERE status IN ('queued','running')"
        )]
        if not ids:
            return
        conn.execute(
            "UPDATE fetch_runs SET status = 'failed', finished_at = ?, current_target = NULL, "
            "error_summary = 'interrupted by a server restart' "
            "WHERE status IN ('queued','running')",
            (datetime.now(timezone.utc).isoformat(),),
        )
        logger.warning("Marked %d orphaned fetch run(s) failed: %s", len(ids), ids)


def start_worker() -> None:
    global _queue, _task
    _reconcile_orphaned_runs()
    _queue = asyncio.Queue()
    _task = asyncio.create_task(_loop(), name="fetch-worker")
    logger.info("Fetch worker started")


async def stop_worker() -> None:
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    logger.info("Fetch worker stopped")


def submit(kind: str, mode: str = "incremental", scope: str = "all",
           scope_arg: str | None = None) -> tuple[int, bool]:
    """Create the run row + enqueue. Returns (run_id, deduped).

    If a run of the same kind is already queued or running, no new job is
    created — the existing run's id is returned so the caller attaches to it.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown fetch kind '{kind}'")
    if _queue is None:
        raise RuntimeError("Fetch worker is not running")
    with get_connection() as conn:
        existing = runs.active_run_for_kind(conn, kind)
        if existing is not None:
            return existing, True
        run_id = runs.create_run(conn, kind, mode, scope, scope_arg)
    _queue.put_nowait(Job(run_id, kind, mode, scope, scope_arg))
    return run_id, False


def queue_depth() -> int:
    return _queue.qsize() if _queue else 0


async def _loop() -> None:
    assert _queue is not None
    while True:
        job = await _queue.get()
        try:
            await _run_job(job)
        except Exception:  # noqa: BLE001 - never let the worker die
            logger.exception("Fetch job %s (%s) crashed", job.run_id, job.kind)
        finally:
            _queue.task_done()


async def _run_job(job: Job) -> None:
    logger.info("Fetch job %s start: %s mode=%s scope=%s", job.run_id, job.kind, job.mode, job.scope)
    with get_connection() as conn:
        runs.mark_running(conn, job.run_id)
        try:
            if job.kind == "asset_catalog":
                await catalog.run_asset_catalog(conn, job.run_id)
            elif job.kind == "asset_prices":
                await prices.run_asset_prices(conn, job.run_id, job.mode, job.scope, job.scope_arg)
            elif job.kind == "crypto_bars":
                await crypto.run_crypto_bars(conn, job.run_id, job.mode)
            elif job.kind == "commodity_prices":
                await commodities.run_commodities(conn, job.run_id, job.mode)
            elif job.kind == "macro":
                await macro.run_macro(conn, job.run_id, job.mode)
            elif job.kind == "memberships":
                await memberships.run_memberships(conn, job.run_id)
            elif job.kind == "option_snapshots":
                await options.run_option_snapshots(conn, job.run_id, job.mode)
            elif job.kind == "signal_universe":
                # pure-CPU engine loop — run off the event loop so progress
                # polling stays responsive
                from app.features.signals import service as signal_service

                await asyncio.to_thread(
                    signal_service.run_universe, conn, job.run_id, job.mode
                )
            else:  # pragma: no cover - guarded by submit()
                raise ValueError(job.kind)

            run = runs.get_run(conn, job.run_id) or {}
            status = "succeeded" if run.get("failed_targets", 0) == 0 else "failed"
            summary = None if status == "succeeded" else f"{run['failed_targets']} target(s) failed"
            runs.finish_run(conn, job.run_id, status, summary)
        except runs.RunCancelled:
            runs.finish_run(conn, job.run_id, "cancelled")
            logger.info("Fetch job %s cancelled", job.run_id)
        except Exception as exc:  # noqa: BLE001
            runs.finish_run(conn, job.run_id, "failed", str(exc)[:300])
            logger.exception("Fetch job %s failed", job.run_id)
    logger.info("Fetch job %s done", job.run_id)
