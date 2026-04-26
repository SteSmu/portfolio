"""OpenRouter wrapper for LLM-generated portfolio insights.

We use OpenRouter (https://openrouter.ai) directly via httpx — same provider
that claude-trader already uses, key shared via the same `.env`. Stays
provider-neutral: we can swap models (Claude / GPT / Gemini) without changing
client code.

Returned objects are JSON dicts compatible with the asset_insights table.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Model defaults — tuned per insight type.
MODEL_SUMMARY = os.getenv("PT_INSIGHT_MODEL_SUMMARY", "anthropic/claude-sonnet-4.5")
MODEL_DEEP = os.getenv("PT_INSIGHT_MODEL_DEEP", "anthropic/claude-opus-4.7")


class LLMError(RuntimeError):
    """Wraps any failure interacting with OpenRouter."""


@dataclass
class LLMResponse:
    """Normalised response. `raw` keeps the OpenRouter envelope for debugging."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw: dict


def _api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise LLMError(
            "OPENROUTER_API_KEY env var not set. Reuse the same key as claude-trader."
        )
    return key


def chat(
    *,
    system: str,
    user: str,
    model: str = MODEL_SUMMARY,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    response_format: dict | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> LLMResponse:
    """Single-turn chat completion via OpenRouter.

    `response_format` lets the caller request strict JSON output:
    `{"type": "json_object"}`. Errors raise `LLMError` with the upstream
    message preserved.
    """
    payload: dict = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/SteSmu/portfolio",
        "X-Title": "Portfolio Tracker",
    }

    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            resp = client.post(OPENROUTER_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenRouter request failed: {exc}") from exc
    latency_ms = int((time.monotonic() - started) * 1000)

    if resp.status_code >= 400:
        raise LLMError(
            f"OpenRouter HTTP {resp.status_code}: {resp.text[:500]}"
        )
    data = resp.json()

    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            raw=data,
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Malformed OpenRouter response: {data!r}") from exc


def chat_json(
    *,
    system: str,
    user: str,
    model: str = MODEL_SUMMARY,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict, LLMResponse]:
    """Same as `chat` but enforces JSON-object output and parses it.

    Returns (parsed_json, raw_response). Raises `LLMError` if the response
    is not valid JSON or doesn't decode to an object.
    """
    resp = chat(
        system=system, user=user, model=model,
        temperature=temperature, max_tokens=max_tokens,
        response_format={"type": "json_object"},
        transport=transport,
    )
    try:
        parsed = json.loads(resp.content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM returned non-JSON content:\n{resp.content[:500]}") from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"LLM returned non-object JSON: {type(parsed).__name__}")
    return parsed, resp
