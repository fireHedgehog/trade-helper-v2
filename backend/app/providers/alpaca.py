"""Alpaca provider: a key ID plus a secret key.

Alpaca issues credentials as a *pair* — an API Key ID that identifies the
key (like a username) and an API Secret Key that authenticates it (like a
password). Both are needed on every request; the secret is shown only once
at creation time. FRED, by contrast, needs only a single key.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from app.core.config import get_settings
from app.providers.base import FieldSpec, ProviderSpec, VerifyResult, register

DESCRIPTION = (
    "Alpaca Markets brokerage & market-data API. Credentials come as a pair: "
    "an API Key ID (identifies the key) and an API Secret Key (authenticates "
    "it). Generate them in the Alpaca dashboard. Verification calls the paper "
    "trading account endpoint — read-only, submits no orders."
)


async def verify(values: Mapping[str, str], spec: ProviderSpec) -> VerifyResult:
    """Read the paper account once to confirm the key pair works."""
    settings = get_settings()
    headers = {
        "APCA-API-KEY-ID": values.get("api_key_id", ""),
        "APCA-API-SECRET-KEY": values.get("api_secret_key", ""),
    }
    url = f"{settings.alpaca_api_base}/v2/account"

    async with httpx.AsyncClient(timeout=settings.verify_timeout_seconds) as client:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            return "invalid", f"Network error: {type(exc).__name__}"

    if resp.status_code == 200:
        return "healthy", "HTTP 200"
    if resp.status_code in (401, 403):
        return "invalid", f"HTTP {resp.status_code} (rejected key pair)"
    return "invalid", f"HTTP {resp.status_code}"


register(
    ProviderSpec(
        key="alpaca",
        label="Alpaca",
        description=DESCRIPTION,
        credential_name="trade-helper/alpaca",
        fields=[
            FieldSpec(
                name="api_key_id",
                label="API Key ID",
                env_var="ALPACA_API_KEY_ID",
                placeholder="e.g. PK... or AK...",
            ),
            FieldSpec(
                name="api_secret_key",
                label="API Secret Key",
                env_var="ALPACA_API_SECRET_KEY",
                placeholder="shown once when you created the key",
            ),
        ],
        verifier=verify,
    )
)
