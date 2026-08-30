"""FRED client — series metadata + observations. Used for macro and for the
commodity reference prices (docs/draft-design/09-…-audit.md §1.5-1.6)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.pacing import get_limiter
from app.providers.clients.http import paced_get_json
from app.providers.secret_resolver import resolve_provider_secrets


class FredClient:
    def __init__(self) -> None:
        s = get_settings()
        self._base = s.fred_api_base.rstrip("/")
        self._api_key = resolve_provider_secrets("fred")["api_key"]
        self._limiter = get_limiter("fred", s.fred_min_interval_seconds)
        self._timeout = s.fetch_timeout_seconds

    async def __aenter__(self) -> "FredClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get_series(self, series_id: str) -> dict:
        """Series metadata (title, units, frequency, observation range, …)."""
        data = await paced_get_json(
            self._client,
            self._limiter,
            f"{self._base}/fred/series",
            params={"series_id": series_id, "api_key": self._api_key, "file_type": "json"},
        )
        seriess = data.get("seriess") or []
        return seriess[0] if seriess else {}

    async def get_observations(
        self,
        series_id: str,
        observation_start: str,
        observation_end: str | None = None,
    ) -> list[dict]:
        """All observations from `observation_start` (one request suffices at
        FRED's 100k limit for any daily series)."""
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "observation_start": observation_start,
            "limit": 100000,
            "sort_order": "asc",
        }
        if observation_end:
            params["observation_end"] = observation_end
        data = await paced_get_json(
            self._client, self._limiter, f"{self._base}/fred/series/observations", params=params
        )
        return data.get("observations") or []
