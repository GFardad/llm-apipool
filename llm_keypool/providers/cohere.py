"""Cohere native API client (not OpenAI-compatible)."""
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .base import CompletionResult
from .headers import collect_rl_headers

BASE_URL = "https://api.cohere.com/v2"
HTTP_429 = 429


def _make_chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _build_chunk(
    chunk_id: str,
    created: int,
    model: str,
    delta_content: str | None = None,
    delta_role: str | None = None,
    finish_reason: str | None = None,
    index: int = 0,
    **extra: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Build an OpenAI-format streaming chunk dict."""
    chunk: dict[str, Any] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
    }
    if delta_content is not None or delta_role is not None or finish_reason is not None:
        delta: dict[str, Any] = {}
        if delta_role is not None:
            delta["role"] = delta_role
        if delta_content is not None:
            delta["content"] = delta_content
        chunk["choices"] = [
            {
                "index": index,
                "delta": delta,
                "finish_reason": finish_reason,
            },
        ]
    chunk.update(extra)
    return chunk


def _simulate_stream(
    key_data: dict[str, Any],
    messages: list[dict[str, Any]],
    **kwargs: Any,  # noqa: ANN401
) -> AsyncGenerator[dict[str, Any], None]:
    """Simulate streaming by calling the non-streaming API and yielding one chunk.

    Cohere does not yet have native streaming support in this client; this
    provides a stream-compatible interface for callers that expect one.
    """
    chunk_id = _make_chunk_id()
    created = int(time.time())
    model = key_data["model"]

    async def _gen() -> AsyncGenerator[dict[str, Any], None]:
        result = await complete(key_data, messages, **kwargs)
        if not isinstance(result, CompletionResult):
            # Streaming branch returned a generator, which shouldn't happen here
            return

        if result.error:
            yield _build_chunk(
                chunk_id, created, model,
                x_error=result.error,
                x_was_429=result.was_429,
            )
            return

        # Yield content as a single chunk
        if result.text:
            yield _build_chunk(
                chunk_id, created, model,
                delta_role="assistant",
                delta_content=result.text,
            )
        # Yield final chunk with finish_reason and usage
        extra: dict[str, Any] = {}
        if result.tokens_used:
            extra["x_tokens_used"] = result.tokens_used
        yield _build_chunk(
            chunk_id, created, model,
            finish_reason="stop",
            **extra,
        )

    return _gen()


async def complete(
    key_data: dict[str, Any],
    messages: list[dict[str, Any]],
    stream: bool = False,
    **kwargs: Any,  # noqa: ANN401
) -> CompletionResult | AsyncGenerator[dict[str, Any], None]:
    """Call Cohere API with the given key and messages.

    When *stream* is ``False`` (default), returns a :class:`CompletionResult`.
    When *stream* is ``True``, returns an async generator that yields dicts in
    OpenAI streaming chunk format.  This is a *simulated* stream — Cohere does
    not currently have native streaming support in this client, so the full
    response is collected first and yielded as a single chunk.
    """
    if stream:
        return _simulate_stream(key_data, messages, **kwargs)

    max_tokens = kwargs.get("max_tokens", 1024)
    temperature = kwargs.get("temperature", 0.7)

    payload = {
        "model": key_data["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        base_url = key_data.get("base_url", BASE_URL)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base_url}/chat", json=payload, headers=headers)
        rl_headers = collect_rl_headers(resp.headers)
        if resp.status_code == HTTP_429:
            return CompletionResult(
                text="", tokens_used=0, was_429=True,
                error="429 rate limit", rate_limit_headers=rl_headers,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data["message"]["content"][0]["text"]
        tokens = data.get("usage", {}).get("tokens", {})
        total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
        return CompletionResult(
            text=text, tokens_used=total, was_429=False, rate_limit_headers=rl_headers,
        )
    except httpx.HTTPStatusError as e:
        return CompletionResult(
            text="", tokens_used=0, was_429=False,
            error=f"HTTP {e.response.status_code}",
        )
    except httpx.TimeoutException:
        return CompletionResult(text="", tokens_used=0, was_429=False, error="Request to Cohere timed out")
    except httpx.NetworkError as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=f"Network error: {str(e)[:100]}")
    # Broad catch to always return structured CompletionResult, not crash
    except Exception as e:  # noqa: BLE001
        return CompletionResult(
            text="", tokens_used=0, was_429=False,
            error=f"Unexpected Cohere error: {type(e).__name__}: {str(e)[:150]}",
        )
