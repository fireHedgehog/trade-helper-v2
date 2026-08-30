"""Alpaca clients — trading API (assets) + market data API (stock/crypto bars).

Pacing/backoff via app.pacing + app.providers.clients.http. Secrets resolved
from the keychain, never logged.
"""

from __future__ import annotations

import urllib.parse

import httpx

from app.core.config import get_settings
from app.pacing import get_limiter
from app.providers.clients.http import paced_get_json
from app.providers.secret_resolver import resolve_provider_secrets


def _auth_headers() -> dict[str, str]:
    creds = resolve_provider_secrets("alpaca")
    return {
        "APCA-API-KEY-ID": creds["api_key_id"],
        "APCA-API-SECRET-KEY": creds["api_secret_key"],
    }


class AlpacaClient:
    def __init__(self) -> None:
        s = get_settings()
        self._trading_base = s.alpaca_api_base.rstrip("/")
        self._data_base = s.alpaca_data_base.rstrip("/")
        self._headers = _auth_headers()
        self._limiter = get_limiter("alpaca", s.alpaca_min_interval_seconds)
        self._timeout = s.fetch_timeout_seconds

    async def __aenter__(self) -> "AlpacaClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    # ---- Trading API ----

    async def list_assets(self, status: str, asset_class: str) -> list[dict]:
        """Full asset list for a status + class (single un-paginated response)."""
        data = await paced_get_json(
            self._client,
            self._limiter,
            f"{self._trading_base}/v2/assets",
            params={"status": status, "asset_class": asset_class},
            headers=self._headers,
        )
        # /v2/assets returns a bare JSON array.
        return data if isinstance(data, list) else []

    # ---- Market Data API ----

    async def get_stock_bars(
        self,
        symbols: list[str],
        start: str,
        end: str,
        adjustment: str,
        timeframe: str = "1Day",
        feed: str = "iex",
    ) -> dict[str, list[dict]]:
        return await self._bars(
            f"{self._data_base}/v2/stocks/bars",
            {
                "symbols": ",".join(symbols),
                "start": start,
                "end": end,
                "timeframe": timeframe,
                "adjustment": adjustment,
                "feed": feed,
                "limit": 10000,
                "sort": "asc",
            },
        )

    async def get_crypto_bars(
        self,
        symbols: list[str],
        start: str,
        end: str,
        timeframe: str = "1Day",
    ) -> dict[str, list[dict]]:
        # Crypto symbols contain "/", keep them readable in the query string.
        joined = ",".join(symbols)
        return await self._bars(
            f"{self._data_base}/v1beta3/crypto/us/bars",
            {
                "symbols": joined,
                "start": start,
                "end": end,
                "timeframe": timeframe,
                "limit": 10000,
                "sort": "asc",
            },
        )

    async def get_option_snapshots(
        self, underlying: str, params: dict
    ) -> dict[str, dict]:
        """Chain snapshot for one underlying (quote + greeks + IV per contract).

        Free plan = `feed=indicative` (15-min delayed). Follows
        `next_page_token`, merging the `snapshots` map keyed by OCC symbol.
        """
        url = f"{self._data_base}/v1beta1/options/snapshots/{underlying}"
        out: dict[str, dict] = {}
        page_token: str | None = None
        base = {"feed": "indicative", "limit": 1000, **params}
        while True:
            page_params = dict(base)
            if page_token:
                page_params["page_token"] = page_token
            data = await paced_get_json(
                self._client, self._limiter, url, params=page_params, headers=self._headers
            )
            for occ, snap in (data.get("snapshots") or {}).items():
                out[occ] = snap
            page_token = data.get("next_page_token")
            if not page_token:
                return out

    async def _bars(self, url: str, params: dict) -> dict[str, list[dict]]:
        """Follow next_page_token, merging the per-symbol bar lists."""
        out: dict[str, list[dict]] = {}
        page_token: str | None = None
        while True:
            page_params = dict(params)
            if page_token:
                page_params["page_token"] = page_token
            data = await paced_get_json(
                self._client, self._limiter, url, params=page_params, headers=self._headers
            )
            for symbol, bars in (data.get("bars") or {}).items():
                out.setdefault(symbol, []).extend(bars or [])
            page_token = data.get("next_page_token")
            if not page_token:
                return out


def encode_crypto_symbol(symbol: str) -> str:
    """BTC/USD -> BTC%2FUSD for path use (not needed for query params)."""
    return urllib.parse.quote(symbol, safe="")
