"""Provider dispatch: selects best key and calls the right provider."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import tiktoken

from openai import APIStatusError

from llm_apipool.core.circuit_breaker import get_circuit_breaker
from llm_apipool.core.metrics import get_metrics
from llm_apipool.core.model_effort import inject_effort_params

from . import cloudflare as _cloudflare
from . import cohere as _cohere
from . import openai_compat
from .base import CompletionResult

STREAM_FIRST_CHUNK_TIMEOUT = 10
_MASK_MIN_LEN = 8
_MASK_SHOW = 4


def _max_attempts_for(rotator: Any) -> int:
    """Calculate max retry attempts based on available active keys.

    Tries every active key at least once, with room for 429 retries.
    """
    all_keys = rotator.store.get_all_keys()
    active = sum(1 for k in all_keys if k.get("is_active"))
    return max(active * 3, 20)


def _mask_key(api_key: str) -> str:
    """Mask API key for safe logging."""
    if len(api_key) <= _MASK_MIN_LEN:
        return "****" + api_key[-_MASK_SHOW:] if len(api_key) > _MASK_SHOW else "****"
    return api_key[:_MASK_SHOW] + "****" + api_key[-_MASK_SHOW:]


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Count tokens using tiktoken (cl100k_base) for accurate audit logging."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
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


async def _prepend_chunk(
    first_chunk: dict[str, Any],
    rest: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield *first_chunk* first, then forward all remaining chunks from *rest*."""
    yield first_chunk
    async for chunk in rest:
        yield chunk


async def complete(
    rotator: Any,
    capabilities: list[str] | None = None,
    messages: list[dict[str, Any]] | None = None,
    subscriber_id: str = "unknown",
    stream: bool = False,
    **kwargs: Any,
) -> (
    tuple[CompletionResult, dict[str, Any] | None]
    | tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any] | None]
):
    messages = messages or []
    min_context = kwargs.pop("min_context", None)
    require_tools = kwargs.pop("require_tools", None)
    require_vision = kwargs.pop("require_vision", None)

    if stream:
        return await _stream_complete(
            rotator,
            capabilities,
            messages,
            subscriber_id,
            min_context,
            require_tools,
            require_vision,
            **kwargs,
        )

    max_attempts = _max_attempts_for(rotator)

    for attempt in range(max_attempts):
        key_data = rotator.get_best_key(
            capabilities,
            subscriber_id=subscriber_id,
            min_context=min_context,
            require_tools=require_tools,
            require_vision=require_vision,
        )
        if not key_data:
            return CompletionResult(
                text="", tokens_used=0, was_429=False, error="all_keys_exhausted"
            ), None

        key_id = key_data["key_id"]
        cb = get_circuit_breaker()
        if not cb.is_allowed(key_data["provider"], key_data.get("model", ""), key_id):
            rotator.skip_key(key_id)
            continue

        inject_effort_params(key_data["provider"], key_data.get("model", ""), kwargs)
        t0 = time.monotonic()
        try:
            result = await _call_complete(key_data, messages, **kwargs)
        except APIStatusError as exc:
            is_429 = exc.status_code == 429
            result = CompletionResult(
                text="",
                tokens_used=0,
                was_429=is_429,
                error=f"API error ({exc.status_code}): {str(exc)[:150]}",
            )
        except Exception as exc:
            result = CompletionResult(
                text="",
                tokens_used=0,
                was_429=False,
                error=f"Unexpected error: {type(exc).__name__}: {str(exc)[:150]}",
            )
        latency_ms = int((time.monotonic() - t0) * 1000)

        if not isinstance(result, CompletionResult):
            return CompletionResult(
                text="", tokens_used=0, was_429=False, error="unexpected_stream_result"
            ), None

        if result.was_429:
            rotator.handle_429(
                key_id,
                key_data["provider"],
                result.rate_limit_headers,
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
            )
            get_metrics().record_request(
                key_data["provider"],
                key_data.get("model", ""),
                key_id,
                0,
                latency_ms,
                was_429=True,
            )
            await asyncio.sleep(min(0.5 * (2**attempt), 5.0))
            continue

        if result.error:
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error=str(result.error)[:200],
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            get_metrics().record_request(
                key_data["provider"],
                key_data.get("model", ""),
                key_id,
                0,
                latency_ms,
                was_error=True,
            )
            await asyncio.sleep(min(0.1 * (2**attempt), 2.0))
            continue

        tokens_in = _estimate_tokens(messages)
        cb.record_success(key_data["provider"], key_data.get("model", ""), key_id)
        rotator.handle_success(
            key_id,
            result.tokens_used,
            result.rate_limit_headers,
            key_data["provider"],
            tokens_in=tokens_in,
            latency_ms=latency_ms,
            subscriber_id=subscriber_id,
            model=key_data.get("model", ""),
        )
        get_metrics().record_request(
            key_data["provider"],
            key_data.get("model", ""),
            key_id,
            result.tokens_used,
            latency_ms,
        )
        return result, key_data

    return CompletionResult(
        text="", tokens_used=0, was_429=False, error="max_retries_exceeded"
    ), None


async def _stream_complete(
    rotator: Any,
    capabilities: list[str] | None,
    messages: list[dict[str, Any]],
    subscriber_id: str,
    min_context: int | None = None,
    require_tools: bool | None = None,
    require_vision: bool | None = None,
    **kwargs: Any,
) -> tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any] | None]:
    max_attempts = _max_attempts_for(rotator)

    for attempt in range(max_attempts):
        key_data = rotator.get_best_key(
            capabilities,
            subscriber_id=subscriber_id,
            min_context=min_context,
            require_tools=require_tools,
            require_vision=require_vision,
        )
        if not key_data:
            return _error_generator("all_keys_exhausted", ""), None

        key_id = key_data["key_id"]

        cb = get_circuit_breaker()
        if not cb.is_allowed(key_data["provider"], key_data.get("model", ""), key_id):
            rotator.skip_key(key_id)
            continue

        inject_effort_params(key_data["provider"], key_data.get("model", ""), kwargs)
        t0 = time.monotonic()

        try:
            result = await _call_complete(key_data, messages, stream=True, **kwargs)
        except APIStatusError as exc:
            is_429 = exc.status_code == 429
            if is_429:
                rotator.handle_429(
                    key_id,
                    key_data["provider"],
                    {},
                    subscriber_id=subscriber_id,
                    model=key_data.get("model", ""),
                )
            else:
                rotator.handle_error(
                    key_id,
                    key_data["provider"],
                    subscriber_id=subscriber_id,
                    model=key_data.get("model", ""),
                    error=f"API error ({exc.status_code}): {str(exc)[:150]}",
                )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            get_metrics().record_request(
                key_data["provider"],
                key_data.get("model", ""),
                key_id,
                0,
                int((time.monotonic() - t0) * 1000),
                was_error=not is_429,
                was_429=is_429,
            )
            continue
        except Exception as exc:
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            get_metrics().record_request(
                key_data["provider"],
                key_data.get("model", ""),
                key_id,
                0,
                int((time.monotonic() - t0) * 1000),
                was_error=True,
            )
            continue

        if not isinstance(result, AsyncGenerator):
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error="non-stream result for streaming call",
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            continue

        # Peek first chunk with timeout — TTFT gate
        try:
            first_chunk = await asyncio.wait_for(
                result.__anext__(), timeout=STREAM_FIRST_CHUNK_TIMEOUT
            )
        except StopAsyncIteration:
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error="empty stream",
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            continue
        except asyncio.TimeoutError:
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error="TTFT timeout",
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            get_metrics().record_request(
                key_data["provider"],
                key_data.get("model", ""),
                key_id,
                0,
                STREAM_FIRST_CHUNK_TIMEOUT * 1000,
                was_error=True,
            )
            continue
        except Exception as exc:
            rotator.handle_error(
                key_id,
                key_data["provider"],
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
            )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            continue

        if first_chunk.get("x_error"):
            if first_chunk.get("x_was_429"):
                rotator.handle_429(
                    key_id,
                    key_data["provider"],
                    {},
                    subscriber_id=subscriber_id,
                    model=key_data.get("model", ""),
                )
            else:
                rotator.handle_error(
                    key_id,
                    key_data["provider"],
                    subscriber_id=subscriber_id,
                    model=key_data.get("model", ""),
                    error=first_chunk.get("x_error", "provider error")[:200],
                )
            cb.record_failure(key_data["provider"], key_data.get("model", ""), key_id)
            continue

        rest = _prepend_chunk(first_chunk, result)
        gen = _wrap_stream_lifecycle(rest, rotator, key_data, subscriber_id, messages)
        return gen, key_data

    return _error_generator("all_keys_exhausted", ""), None


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


async def _wrap_stream_lifecycle(
    provider_gen: AsyncGenerator[dict[str, Any], None],
    rotator: Any,
    key_data: dict[str, Any],
    subscriber_id: str,
    messages: list[dict[str, Any]],
) -> AsyncGenerator[dict[str, Any], None]:
    """Wrap a streaming provider generator with rotator lifecycle management."""
    t0 = time.monotonic()
    tokens_in = _estimate_tokens(messages)
    tokens_used = 0
    had_error = False
    key_id = key_data.get("key_id", -1)
    provider = key_data.get("provider", "")
    model = key_data.get("model", "")

    try:
        async for chunk in provider_gen:
            if "x_tokens_used" in chunk:
                tokens_used = chunk["x_tokens_used"]
            x_err = chunk.get("x_error")
            if x_err:
                had_error = True
                if chunk.get("x_was_429"):
                    rotator.handle_429(
                        key_id, provider, {}, subscriber_id=subscriber_id, model=model
                    )
                else:
                    rotator.handle_error(
                        key_id,
                        provider,
                        subscriber_id=subscriber_id,
                        model=model,
                        error=str(x_err)[:200],
                    )
            yield chunk

        latency_ms = int((time.monotonic() - t0) * 1000)
        get_metrics().record_request(
            provider,
            model,
            key_id,
            tokens_used,
            latency_ms,
            was_error=had_error,
            was_429=had_error,
        )

        if not had_error:
            rotator.handle_success(
                key_id,
                tokens_used=tokens_used,
                provider=provider,
                tokens_in=tokens_in,
                latency_ms=latency_ms,
                subscriber_id=subscriber_id,
                model=model,
            )
    except Exception:
        rotator.handle_error(
            key_id,
            provider,
            subscriber_id=subscriber_id,
            model=model,
            error="stream exception",
        )
        raise


async def _call_complete(
    key_data: dict[str, Any],
    messages: list[dict[str, Any]],
    stream: bool = False,
    **kwargs: Any,
) -> CompletionResult | AsyncGenerator[dict[str, Any], None]:
    provider = key_data.get("provider", "")
    openai_compatible = key_data.get("openai_compatible", True)

    if stream:
        if openai_compatible:
            return await openai_compat.complete(
                key_data, messages, stream=True, **kwargs
            )
        if provider == "cohere":
            return await _cohere.complete(key_data, messages, stream=True, **kwargs)
        if provider == "cloudflare":
            return await _cloudflare.complete(key_data, messages, stream=True, **kwargs)
        return _error_generator(
            f"no client for provider '{provider}'", key_data.get("model", "")
        )

    if openai_compatible:
        return await openai_compat.complete(key_data, messages, **kwargs)
    if provider == "cohere":
        return await _cohere.complete(key_data, messages, **kwargs)
    if provider == "cloudflare":
        return await _cloudflare.complete(key_data, messages, **kwargs)
    return CompletionResult(
        text="",
        tokens_used=0,
        was_429=False,
        error=f"no client for provider '{provider}'",
    )
