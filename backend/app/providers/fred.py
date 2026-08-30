"""FRED provider: a single API key."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from app.core.config import get_settings
from app.providers.base import FieldSpec, ProviderSpec, VerifyResult, register

DESCRIPTION = (
    "Federal Reserve Economic Data (St. Louis Fed). Uses a single API key — "
    "request one free at https://fredaccount.stlouisfed.org/apikeys."
)


async def verify(values: Mapping[str, str], spec: ProviderSpec) -> VerifyResult:
    """Make one minimal read call to confirm the key works."""
    settings = get_settings()
    api_key = values.get("api_key", "")
    url = f"{settings.fred_api_base}/fred/series"
    params = {"series_id": "GNPCA", "api_key": api_key, "file_type": "json"}

    async with httpx.AsyncClient(timeout=settings.verify_timeout_seconds) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.RequestError as exc:
            return "invalid", f"Network error: {type(exc).__name__}"

    if resp.status_code == 200:
        return "healthy", "HTTP 200"
    if resp.status_code == 400:
        # FRED returns 400 with an error message for a bad/blocked API key.
        return "invalid", "HTTP 400 (bad or blocked API key)"
    return "invalid", f"HTTP {resp.status_code}"


register(
    ProviderSpec(
        key="fred",
        label="FRED",
        description=DESCRIPTION,
        credential_name="trade-helper/fred",
        fields=[
            FieldSpec(
                name="api_key",
                label="API Key",
                env_var="FRED_API_KEY",
                placeholder="32-character key",
            ),
        ],
        verifier=verify,
    )
)
