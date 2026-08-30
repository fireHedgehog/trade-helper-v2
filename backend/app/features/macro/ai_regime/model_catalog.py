"""Model catalogue + token-budget presets for the AI regime dropdown.

Reads models.toml at run time. Also fetches the account's real model ids from
OpenAI /v1/models so the UI can flag which catalogue rows are actually usable.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.providers.secret_resolver import MissingCredential, resolve_provider_secrets

MODELS_PATH = Path(__file__).with_name("models.toml")

# Heuristic: which /v1/models ids are usable as chat models here.
_CHAT_HINTS = ("gpt-", "o1", "o3", "o4", "chatgpt")
_NON_CHAT = ("embedding", "whisper", "tts", "audio", "dall-e", "image", "moderation", "realtime")


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    family: str
    tier: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    default: bool
    enabled: bool
    available_on_account: bool | None = None  # None = not checked

    def est_cost_usd(self, in_tokens: int, out_tokens: int) -> float:
        return (
            in_tokens / 1_000_000 * self.input_usd_per_1m
            + out_tokens / 1_000_000 * self.output_usd_per_1m
        )


@dataclass(frozen=True)
class BudgetPreset:
    key: str
    label: str
    snapshot_detail: str
    rate_series_points: int
    personas: list[str]
    rebuttal_round: bool
    persona_max_tokens: int
    reconciler_max_tokens: int
    est_total_tokens: int


def _raw() -> dict:
    return tomllib.loads(MODELS_PATH.read_text(encoding="utf-8"))


def load_models() -> list[ModelOption]:
    data = _raw()
    out: list[ModelOption] = []
    for m in data.get("model", []):
        out.append(
            ModelOption(
                id=m["id"],
                label=m.get("label", m["id"]),
                family=str(m.get("family", "")),
                tier=m.get("tier", "standard"),
                input_usd_per_1m=float(m.get("input_usd_per_1m", 0.0)),
                output_usd_per_1m=float(m.get("output_usd_per_1m", 0.0)),
                default=bool(m.get("default", False)),
                enabled=bool(m.get("enabled", True)),
            )
        )
    return out


def load_budgets() -> list[BudgetPreset]:
    data = _raw().get("budget", {})
    out: list[BudgetPreset] = []
    for key in ("small", "medium", "large"):
        b = data.get(key)
        if not b:
            continue
        out.append(
            BudgetPreset(
                key=key,
                label=b.get("label", key.title()),
                snapshot_detail=b["snapshot_detail"],
                rate_series_points=int(b.get("rate_series_points", 0)),
                personas=list(b.get("personas", [])),
                rebuttal_round=bool(b.get("rebuttal_round", False)),
                persona_max_tokens=int(b.get("persona_max_tokens", 260)),
                reconciler_max_tokens=int(b.get("reconciler_max_tokens", 420)),
                est_total_tokens=int(b.get("est_total_tokens", 0)),
            )
        )
    return out


def default_model_id() -> str:
    for m in load_models():
        if m.default and m.enabled:
            return m.id
    return get_settings().openai_model


async def account_chat_models() -> list[str]:
    """Chat-capable model ids exposed by the configured OpenAI key."""
    settings = get_settings()
    try:
        api_key = resolve_provider_secrets("openai")["api_key"]
    except MissingCredential:
        return []
    url = f"{settings.openai_api_base}/v1/models"
    async with httpx.AsyncClient(timeout=settings.verify_timeout_seconds) as client:
        try:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.RequestError:
            return []
    if resp.status_code != 200:
        return []
    ids = [m["id"] for m in resp.json().get("data", [])]
    return sorted(
        i for i in ids
        if any(h in i for h in _CHAT_HINTS) and not any(n in i for n in _NON_CHAT)
    )
