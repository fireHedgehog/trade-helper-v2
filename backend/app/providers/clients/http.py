"""Shared HTTP GET with pacing + polite retry/backoff for fetch clients."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings
from app.pacing import HostLimiter

logger = logging.getLogger(__name__)


class FetchHTTPError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


async def paced_get_json(
    client: httpx.AsyncClient,
    limiter: HostLimiter,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """GET returning parsed JSON, spaced by `limiter`, retrying 429/5xx."""
    settings = get_settings()
    attempt = 0
    while True:
        attempt += 1
        async with limiter:
            try:
                resp = await client.get(url, params=params, headers=headers)
            except httpx.RequestError as exc:
                if attempt > settings.fetch_max_retries:
                    raise FetchHTTPError(0, f"network error: {type(exc).__name__}") from exc
                await asyncio.sleep(_backoff(attempt))
                continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt > settings.fetch_max_retries:
                raise FetchHTTPError(resp.status_code, resp.text[:200])
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else _backoff(attempt)
            logger.warning("HTTP %s on %s — retry %d in %.1fs", resp.status_code, url, attempt, delay)
            await asyncio.sleep(delay)
            continue

        # 4xx other than 429 — not retryable.
        raise FetchHTTPError(resp.status_code, resp.text[:200])


def _backoff(attempt: int) -> float:
    return min(2.0 ** attempt, 60.0)
