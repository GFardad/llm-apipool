"""Provider dispatch: selects best key and calls the right provider."""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import tiktoken

from . import cloudflare as _cloudflare
from . import cohere as _cohere
from . import openai_compat
from .base import CompletionResult

MAX_RETRY_ATTEMPTS = 10
_MASK_MIN_LEN = 8
_MASK_SHOW = 4


def _mask_key(api_key: str) -> str:
    """Mask API key for safe logging."""
    if len(api_key) <= _MASK_MIN_LEN:
        return "****" + api_key[-_MASK_SHOW:] if len(api_key) > _MASK_SHOW else "****"
    return api_key[:_MASK_SHOW] + "****" + api_key[-_MASK_SHOW:]


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Count tokens using tiktoken (cl100k_base) for accurate audit logging."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:  # noqa: BLE001
        # Fallback: roughly estimate as chars/4
        return sum(len(m.get("content", "")) // 4 for m in messages)
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text", "")
                    total += len(enc.encode(text))
    return total


def _make_chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


async def complete(
    rotator: Any,  # noqa: ANN401
    capabilities: list[str] | None = None,
    messages: list[dict[str, Any]] | None = None,
    subscriber_id: str = "unknown",
    stream: bool = False,
    **kwargs: Any,  # noqa: ANN401
) -> tuple[CompletionResult, dict[str, Any] | None] | tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any] | None]:
    """Select best key, call provider, auto-rotate on 429.

    When *stream* is ``False`` (default):
        Returns ``(CompletionResult, key_data_used)`` — key_data is ``None``
        when all keys are exhausted.

    When *stream* is ``True``:
        Returns ``(async_generator, key_data)``.  The generator yields dicts in
        OpenAI streaming chunk format.  A single attempt is made — no retries
        on 429 (streaming connections cannot be easily retried).  On 429 an
        error chunk is yielded and the generator ends.
    """
    messages = messages or []

    if stream:
        return await _stream_complete(rotator, capabilities, messages, subscriber_id, **kwargs)

    # Type guard: we are in the non-streaming branch
    assert not stream
    for attempt in range(MAX_RETRY_ATTEMPTS):
        key_data = rotator.get_best_key(capabilities, subscriber_id=subscriber_id)
        if not key_data:
            return CompletionResult(text="", tokens_used=0, was_429=False, error="all_keys_exhausted"), None

        t0 = time.monotonic()
        result = await _call_complete(key_data, messages, **kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        if not isinstance(result, CompletionResult):
            # Streaming branch returned a generator, which shouldn't happen in non-streaming mode
            return CompletionResult(text="", tokens_used=0, was_429=False, error="unexpected_stream_result"), None

        if result.was_429:
            rotator.handle_429(
                key_data["key_id"],
                key_data["provider"],
                result.rate_limit_headers,
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
            )
            await asyncio.sleep(min(0.5 * (2 ** attempt), 5.0))
            continue

        # estimate tokens_in using tiktoken for accurate audit logging
        tokens_in = _estimate_tokens(messages)

        rotator.handle_success(
            key_data["key_id"],
            result.tokens_used,
            result.rate_limit_headers,
            key_data["provider"],
            tokens_in=tokens_in,
            latency_ms=latency_ms,
            subscriber_id=subscriber_id,
            model=key_data.get("model", ""),
        )
        return result, key_data

    return CompletionResult(text="", tokens_used=0, was_429=False, error="max_retries_exceeded"), None


async def _stream_complete(
    rotator: Any,  # noqa: ANN401
    capabilities: list[str] | None,
    messages: list[dict[str, Any]],
    subscriber_id: str,
    **kwargs: Any,  # noqa: ANN401
) -> tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any] | None]:
    """Handle streaming completion — single attempt, no retry on 429."""
    key_data = rotator.get_best_key(capabilities, subscriber_id=subscriber_id)
    if not key_data:
        return _error_generator("all_keys_exhausted", ""), None

    gen = await _call_complete(key_data, messages, stream=True, **kwargs)
    # gen is AsyncGenerator here (stream=True)
    return gen, key_data  # type: ignore[return-value]


def _error_generator(error: str, model: str) -> AsyncGenerator[dict[str, Any], None]:
    """Return a single-chunk generator that yields an error then ends."""

    async def _gen() -> AsyncGenerator[dict[str, Any], None]:
        yield {
            "id": _make_chunk_id(),
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [],
            "x_error": error,
        }

    return _gen()


async def _call_complete(key_data: dict[str, Any], messages: list[dict[str, Any]], stream: bool = False, **kwargs: Any) -> CompletionResult | AsyncGenerator[dict[str, Any], None]:  # noqa: ANN401
    if stream:
        if key_data["openai_compatible"]:
            return await openai_compat.complete(key_data, messages, stream=True, **kwargs)
        if key_data["provider"] == "cohere":
            return await _cohere.complete(key_data, messages, stream=True, **kwargs)
        if key_data["provider"] == "cloudflare":
            return await _cloudflare.complete(key_data, messages, stream=True, **kwargs)
        return _error_generator(f"no client for provider '{key_data['provider']}'", key_data.get("model", ""))

    if key_data["openai_compatible"]:
        return await openai_compat.complete(key_data, messages, **kwargs)
    if key_data["provider"] == "cohere":
        return await _cohere.complete(key_data, messages, **kwargs)
    if key_data["provider"] == "cloudflare":
        return await _cloudflare.complete(key_data, messages, **kwargs)
    return CompletionResult(
        text="", tokens_used=0, was_429=False,
        error=f"no client for provider '{key_data['provider']}'",
    )
