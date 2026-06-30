"""SSE benchmark endpoint — streams results as each key completes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from llm_apipool.core.benchmark import BenchmarkRunner
from llm_apipool.providers.dispatch import call_complete


def _load_provider_configs() -> dict[str, Any]:
    """Load provider definitions from the config file."""
    config_path = (
        Path(__file__).resolve().parent.parent.parent / "config" / "providers.json"
    )
    with config_path.open() as f:
        return json.load(f)["providers"]


def _build_key_data(db_key: dict[str, Any], configs: dict[str, Any]) -> dict[str, Any]:
    """Merge a DB key record with its provider config.

    Adds ``base_url``, ``openai_compatible``, and ``no_auth`` from the
    provider definition so the key can be passed directly to
    :func:`call_complete`.
    """
    provider = db_key.get("provider", "")
    cfg = configs.get(provider, {})
    key_data = dict(db_key)
    key_data.setdefault("base_url", cfg.get("base_url", ""))
    key_data.setdefault("openai_compatible", cfg.get("openai_compatible", True))
    key_data.setdefault("no_auth", cfg.get("no_auth", False))
    return key_data


async def _dispatch_wrapper(
    key_data: dict[str, Any],
    model: str,
    messages: list[dict[str, Any]],
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Call a provider's non-streaming completion and return a result dict."""
    merged_params = dict(params) if params else {}
    merged_params.pop("model", None)

    result = await call_complete(
        key_data,
        messages,
        stream=False,
        model=model,
        **merged_params,
    )

    return {
        "content": result.text,
        "tokens_out": result.tokens_used,
        "ttft_ms": None,
    }


def _create_benchmark_router(store: Any = None) -> APIRouter:
    """Create a benchmark router that streams results via SSE.

    Parameters
    ----------
    store:
        A :class:`KeyStore` instance used to look up registered keys.
    """
    configs = _load_provider_configs()
    router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

    @router.get("/run")
    async def run_benchmark(
        key_ids: str = Query(..., description="Comma-separated key IDs"),
        prompt: str = Query(..., description="Test prompt"),
        model: str | None = Query(None),
    ):
        """SSE endpoint — benchmarks selected keys and streams results."""
        ids = [int(k.strip()) for k in key_ids.split(",") if k.strip()]

        keys = []
        for kid in ids:
            k = store.get_key_by_id(kid) if hasattr(store, "get_key_by_id") else None
            if k:
                keys.append(_build_key_data(k, configs))

        if not keys:
            return {"error": "No valid keys found"}

        messages = [{"role": "user", "content": prompt}]
        params: dict[str, Any] = {}
        if model:
            params["model"] = model

        runner = BenchmarkRunner()

        async def event_stream():
            async for event in runner.run_benchmark(
                keys=keys,
                messages=messages,
                params=params,
                dispatch_fn=_dispatch_wrapper,
            ):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router


__all__ = ["_create_benchmark_router"]
