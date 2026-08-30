"""Per-host request pacing.

One in-flight request per host at a time, with a minimum interval between
requests. The fetch worker is already a single asyncio task, so this only
has to enforce spacing — but the lock also guarantees no accidental overlap.
"""

from __future__ import annotations

import asyncio
import time


class HostLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def __aenter__(self) -> "HostLimiter":
        await self._lock.acquire()
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._last = time.monotonic()
        self._lock.release()


_limiters: dict[str, HostLimiter] = {}


def get_limiter(host: str, min_interval_seconds: float) -> HostLimiter:
    limiter = _limiters.get(host)
    if limiter is None:
        limiter = HostLimiter(min_interval_seconds)
        _limiters[host] = limiter
    return limiter
