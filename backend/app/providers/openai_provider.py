"""OpenAI provider: a single API key.

Used by the Macro page's AI risk-on/off estimate (a few cheap-model calls on
a button press). Only stored/verified here; the raw key never leaves the OS
keychain.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from app.core.config import get_settings
from app.providers.base import FieldSpec, ProviderSpec, VerifyResult, register

DESCRIPTION = (
    "OpenAI API key, used for the Macro page's AI regime estimate (a few "
    "cheap-model calls, on demand). Single key from "
    "https://platform.openai.com/api-keys. An OpenAI-compatible base URL can "
    "be set via OPENAI_API_BASE."
)


async def verify(values: Mapping[str, str], spec: ProviderSpec) -> VerifyResult:
    """List models once to confirm the key works. Read-only, no generation."""
    settings = get_settings()
    api_key = values.get("api_key", "")
    url = f"{settings.openai_api_base}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=settings.verify_timeout_seconds) as client:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            return "invalid", f"Network error: {type(exc).__name__}"

    if resp.status_code == 200:
        return "healthy", "HTTP 200"
    if resp.status_code in (401, 403):
        return "invalid", f"HTTP {resp.status_code} (rejected key)"
    return "invalid", f"HTTP {resp.status_code}"


register(
    ProviderSpec(
        key="openai",
        label="OpenAI",
        description=DESCRIPTION,
        credential_name="trade-helper/openai",
        fields=[
            FieldSpec(
                name="api_key",
                label="API Key",
                env_var="OPENAI_API_KEY",
                placeholder="sk-...",
            ),
        ],
        verifier=verify,
    )
)
