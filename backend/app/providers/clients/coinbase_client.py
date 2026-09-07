"""Public Coinbase Exchange daily trade candles; no credentials required."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.pacing import get_limiter
from app.providers.clients.http import paced_get_json


class CoinbaseClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base = settings.coinbase_api_base.rstrip("/")
        self._timeout = settings.fetch_timeout_seconds
        self._limiter = get_limiter("coinbase", settings.coinbase_min_interval_seconds)
        self.requests_made = 0

    async def __aenter__(self) -> CoinbaseClient:
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get_crypto_bars(
        self, symbol: str, start: str, end: str,
        check_cancel: Callable[[], None] = lambda: None,
    ) -> list[dict]:
        """Fetch inclusive UTC dates in <=300-candle requests, sorted and deduped.

        Coinbase can return candles outside the requested interval. Keep only
        requested completed days. Empty periods before a product's listing are
        allowed; the caller checks coverage before replacing stored history.
        """
        product = {"BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD"}[symbol]
        cursor, last = date.fromisoformat(start), date.fromisoformat(end)
        by_date: dict[str, dict] = {}
        while cursor <= last:
            check_cancel()
            stop = min(cursor + timedelta(days=299), last)
            self.requests_made += 1
            payload = await paced_get_json(
                self._client, self._limiter, f"{self._base}/products/{product}/candles",
                params={"granularity": 86400, "start": cursor.isoformat() + "T00:00:00Z",
                        "end": stop.isoformat() + "T00:00:00Z"},
            )
            if not isinstance(payload, list):
                raise ValueError(f"Unexpected Coinbase candle response for {symbol}")
            for row in payload:
                if not isinstance(row, list) or len(row) != 6:
                    raise ValueError(f"Malformed Coinbase candle for {symbol}")
                timestamp, low, high, opening, close, volume = map(float, row)
                if not math.isfinite(timestamp) or timestamp % 86400:
                    raise ValueError(f"Invalid daily candle timestamp for {symbol}")
                day = datetime.fromtimestamp(timestamp, timezone.utc).date()
                if not cursor <= day <= stop:
                    continue
                if (not all(math.isfinite(v) for v in (low, high, opening, close, volume))
                        or not 0 < low <= min(opening, close) <= max(opening, close) <= high
                        or volume < 0):
                    raise ValueError(f"Invalid Coinbase OHLCV for {symbol} on {day}")
                bar = {"t": day.isoformat() + "T00:00:00Z", "o": opening,
                       "h": high, "l": low, "c": close, "v": volume}
                key = day.isoformat()
                if key in by_date and by_date[key] != bar:
                    raise ValueError(f"Conflicting Coinbase candles for {symbol} on {day}")
                by_date[key] = bar
            cursor = stop + timedelta(days=1)
        return [by_date[key] for key in sorted(by_date)]
