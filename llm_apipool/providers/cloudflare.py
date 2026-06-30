"""Cloudflare Workers AI client."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from ._stream_utils import build_chunk, make_chunk_id
from .base import CompletionResult
from .headers import collect_rl_headers

HTTP_429 = 429


async def _real_stream(
    key_data: dict[str, Any],
    messages: list[dict[str, Any]],
    **kwargs: Any,  # noqa: ANN401
) -> AsyncGenerator[dict[str, Any], None]:
    """Real SSE streaming for Cloudflare Workers AI.

    Calls the Cloudflare Workers AI endpoint with ``stream: True`` and
    yields OpenAI-format streaming chunks from the SSE event stream.
    """
    chunk_id = make_chunk_id()
    created = int(time.time())
    model = key_data["model"]
    url = f"{key_data['base_url']}/{model}"

    payload = {
        "messages": messages,
        "max_tokens": kwargs.get("max_tokens", 1024),
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code == HTTP_429:
                    yield build_chunk(
                        chunk_id,
                        created,
                        model,
                        x_error="429 rate limit",
                        x_was_429=True,
                    )
                    return
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield build_chunk(
                            chunk_id,
                            created,
                            model,
                            finish_reason="stop",
                        )
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    text = data.get("response", "") or data.get("text", "")
                    if text:
                        yield build_chunk(
                            chunk_id,
                            created,
                            model,
                            delta_content=text,
                            delta_role="assistant",
                        )
    except httpx.HTTPStatusError as e:
        yield build_chunk(
            chunk_id,
            created,
            model,
            x_error=f"HTTP {e.response.status_code}",
        )
    except httpx.TimeoutException:
        yield build_chunk(
            chunk_id,
            created,
            model,
            x_error="Request to Cloudflare timed out",
        )
    except httpx.RequestError as e:
        yield build_chunk(
            chunk_id,
            created,
            model,
            x_error=f"Request error: {str(e)[:100]}",
        )
    except Exception as e:  # noqa: BLE001
        yield build_chunk(
            chunk_id,
            created,
            model,
            x_error=f"Unexpected Cloudflare error: {type(e).__name__}: {str(e)[:150]}",
        )


async def complete(
    key_data: dict[str, Any],
    messages: list[dict[str, Any]],
    stream: bool = False,
    **kwargs: Any,  # noqa: ANN401
) -> CompletionResult | AsyncGenerator[dict[str, Any], None]:
    """Call Cloudflare Workers AI with the given key and messages.

    When *stream* is ``False`` (default), returns a :class:`CompletionResult`.
    When *stream* is ``True``, returns an async generator that yields dicts in
    OpenAI streaming chunk format using real SSE streaming.
    """
    if stream:
        return _real_stream(key_data, messages, **kwargs)

    model = key_data["model"]
    url = f"{key_data['base_url']}/{model}"
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": messages,
        "max_tokens": kwargs.get("max_tokens", 1024),
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
        rl_headers = collect_rl_headers(resp.headers)
        if resp.status_code == HTTP_429:
            return CompletionResult(
                text="",
                tokens_used=0,
                was_429=True,
                error="429 rate limit",
                rate_limit_headers=rl_headers,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("result", {}).get("response", "")
        return CompletionResult(
            text=text,
            tokens_used=0,
            was_429=False,
            rate_limit_headers=rl_headers,
        )
    except httpx.HTTPStatusError as e:
        return CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error=f"HTTP {e.response.status_code}",
        )
    except httpx.TimeoutException:
        return CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="Request to Cloudflare timed out",
        )
    except httpx.RequestError as e:
        return CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error=f"Request error: {str(e)[:100]}",
        )
    except Exception as e:  # noqa: BLE001
        return CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error=f"Unexpected Cloudflare error: {type(e).__name__}: {str(e)[:150]}",
        )
