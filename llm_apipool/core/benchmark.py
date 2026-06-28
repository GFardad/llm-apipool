"""Benchmark runner — tests API keys against real prompts and reports timing."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator


class BenchmarkRunner:
    """Runs benchmark requests against selected keys sequentially.

    Each key is tested in order. Results stream as an async generator
    of event dicts (``start``, ``result``, ``error``, ``complete``).
    """

    async def run_benchmark(
        self,
        keys: list[dict[str, Any]],
        messages: list[dict[str, str]],
        params: dict[str, Any] | None = None,
        dispatch_fn: Any = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run a benchmark for each key sequentially.

        For each key:
        1. Yield a ``start`` event.
        2. Call *dispatch_fn* with a 30-second timeout.
        3. Measure TTFT, total latency, tokens/sec.
        4. Yield a ``result`` or ``error`` event.
        5. Yield a ``complete`` event when all keys are done.

        Global timeout: 300 seconds.

        Parameters
        ----------
        keys:
            List of key dicts. Each must have at least ``id``, ``provider``,
            and ``model``.
        messages:
            Chat messages to send (e.g. ``[{"role": "user", "content": …}]``).
        params:
            Optional extra parameters forwarded to *dispatch_fn*.
        dispatch_fn:
            Async callable ``(key_data, model, messages, params) -> dict``.
            Must return a dict with ``content``, ``tokens_out``, and
            optionally ``ttft_ms``.
        """
        start_time = time.monotonic()
        total = len(keys)

        for i, key_data in enumerate(keys):
            key_id = key_data.get("id", i)
            provider = key_data.get("provider", "unknown")
            model = key_data.get("model", "unknown")

            yield {
                "type": "start",
                "key_id": key_id,
                "provider": provider,
                "model": model,
                "index": i,
                "total": total,
            }

            try:
                t0 = time.monotonic()

                result = await asyncio.wait_for(
                    dispatch_fn(key_data, model, messages, params),
                    timeout=30.0,
                )

                t1 = time.monotonic()
                latency_ms = (t1 - t0) * 1000

                response_text = (
                    result.get("content", "") if isinstance(result, dict) else str(result)
                )
                token_count = (
                    result.get("tokens_out", 0) if isinstance(result, dict) else 0
                )
                ttft_ms = (
                    result.get("ttft_ms", latency_ms)
                    if isinstance(result, dict)
                    else latency_ms
                )
                tokens_per_sec = (
                    (token_count / (latency_ms / 1000)) if latency_ms > 0 else 0
                )

                truncated = response_text[:500] + "..." if len(str(response_text)) > 500 else response_text

                yield {
                    "type": "result",
                    "key_id": key_id,
                    "provider": provider,
                    "model": model,
                    "ttft_ms": round(ttft_ms, 1),
                    "latency_ms": round(latency_ms, 1),
                    "tokens_per_sec": round(tokens_per_sec, 1),
                    "token_count": token_count,
                    "success": True,
                    "response_text": truncated,
                }

            except asyncio.TimeoutError:
                yield {
                    "type": "error",
                    "key_id": key_id,
                    "provider": provider,
                    "model": model,
                    "error": "Timeout (>30s)",
                }
            except Exception as e:
                yield {
                    "type": "error",
                    "key_id": key_id,
                    "provider": provider,
                    "model": model,
                    "error": str(e)[:200],
                }

        total_time = (time.monotonic() - start_time) * 1000
        yield {
            "type": "complete",
            "total_time_ms": round(total_time, 1),
            "keys_tested": total,
        }


__all__ = ["BenchmarkRunner"]
