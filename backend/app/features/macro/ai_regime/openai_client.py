"""Minimal OpenAI chat-completions caller for the AI regime run.

One helper: `chat()` sends system + user, returns (text, prompt_tokens,
completion_tokens). Retries once without params a newer model may reject.
"""

from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.providers.secret_resolver import resolve_provider_secrets


class OpenAIError(RuntimeError):
    pass


async def chat(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    temperature: float,
    force_json: bool = True,
    timeout: float = 90.0,
) -> tuple[str, int, int]:
    settings = get_settings()
    api_key = resolve_provider_secrets("openai")["api_key"]
    url = f"{settings.openai_api_base}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code == 400:
            # Newer/reasoning models reject temperature or response_format —
            # retry once with a minimal body.
            minimal = {
                "model": model,
                "messages": body["messages"],
                "max_completion_tokens": max_tokens,
            }
            resp = await client.post(url, headers=headers, json=minimal)
        if resp.status_code != 200:
            raise OpenAIError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise OpenAIError(f"unexpected response shape: {json.dumps(data)[:300]}") from exc
    usage = data.get("usage") or {}
    return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


async def web_chat(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    timeout: float = 120.0,
) -> tuple[str, int, int]:
    """One Responses API call with web search for the catalyst overlay only."""
    settings = get_settings()
    api_key = resolve_provider_secrets("openai")["api_key"]
    url = f"{settings.openai_api_base}/v1/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "instructions": system,
        "input": user,
        "tools": [{"type": "web_search_preview", "search_context_size": "medium"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": max_tokens,
        "store": False,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        raise OpenAIError(f"web search HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    parts: list[str] = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    text = "\n".join(parts)
    if not text:
        raise OpenAIError(f"unexpected web-search response shape: {json.dumps(data)[:300]}")
    usage = data.get("usage") or {}
    return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a completion (handles ``` fences)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise OpenAIError(f"no JSON object in completion: {text[:200]}")
    return json.loads(t[start : end + 1])
