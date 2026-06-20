"""OpenAI-compatible HTTP proxy for llm-keypool."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm_keypool.key_store import KeyStore
from llm_keypool.providers.dispatch import _estimate_tokens, complete
from llm_keypool.rotator import Rotator

_MASK_MIN_LEN = 8
_MASK_SHOW = 4


def _mask_key(api_key: str) -> str:
    """Mask an API key for safe logging."""
    if len(api_key) <= _MASK_MIN_LEN:
        return "****" + api_key[-_MASK_SHOW:] if len(api_key) > _MASK_SHOW else "****"
    return api_key[:_MASK_SHOW] + "****" + api_key[-_MASK_SHOW:]


def _load_provider_configs() -> dict[str, Any]:
    config_path = Path(__file__).parent / "config" / "providers.json"
    with config_path.open() as f:
        return json.load(f)["providers"]  # type: ignore[no-any-return]


class _ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool | None = False


def make_app(  # noqa: C901, PLR0915
    capabilities: list[str] | None = None,
    rotate_every: int = 5,
    quality_tier: int = 1,
    max_fallback_tier: int = 4,
) -> FastAPI:
    """Build a FastAPI app with OpenAI-compatible endpoints and model quality routing.

    Parameters
    ----------
    capabilities:
        Default capabilities to use when the ``X-Keypool-Capabilities`` header
        is absent.
    rotate_every:
        Requests per key before rotating.
    quality_tier:
        Preferred model quality tier (1 = best). The rotator picks keys
        from this tier first and falls back through worse tiers when
        keys are exhausted.
    max_fallback_tier:
        Worst quality tier the rotator is allowed to fall back to (inclusive).

    """
    if capabilities is None:
        capabilities = ["general_purpose"]

    store = KeyStore()
    configs = _load_provider_configs()
    rotator = Rotator(
        store,
        configs,
        rotate_every=rotate_every,
        quality_tier=quality_tier,
        max_fallback_tier=max_fallback_tier,
    )

    app = FastAPI(title="llm-keypool proxy", version="2.0")

    @app.post("/v1/chat/completions")
    async def chat_completions(
        req: _ChatRequest,
        x_keypool_capabilities: Annotated[str | None, Header()] = None,
        x_subscriber_id: Annotated[str | None, Header()] = None,
    ) -> Any:  # noqa: ANN401
        # resolve capabilities: header overrides server default
        if x_keypool_capabilities:
            caps = [c.strip() for c in x_keypool_capabilities.split(",") if c.strip()]
        else:
            caps = capabilities

        subscriber = x_subscriber_id or "proxy"

        kwargs: dict[str, Any] = {}
        if req.max_tokens is not None:
            kwargs["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature

        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if req.stream:
            gen, key_data = await complete(
                rotator,
                capabilities=caps,
                messages=req.messages,
                subscriber_id=subscriber,
                stream=True,
                **kwargs,
            )
            if key_data is None:
                raise HTTPException(status_code=503, detail="All available keys exhausted")

            model_used = key_data.get("model") or req.model or "unknown"
            provider_used = key_data.get("provider", "unknown")

            async def _stream() -> AsyncGenerator[str, None]:
                async for chunk in gen:  # type: ignore[union-attr]
                    # Ensure required OpenAI chunk fields are present
                    if "id" not in chunk:
                        chunk["id"] = resp_id
                    if "created" not in chunk:
                        chunk["created"] = created
                    if "model" not in chunk:
                        chunk["model"] = model_used
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                _stream(),
                media_type="text/event-stream",
                headers={"X-Key-Provider": provider_used},
            )

        result, key_data = await complete(
            rotator,
            capabilities=caps,
            messages=req.messages,
            subscriber_id=subscriber,
            **kwargs,
        )

        if result.error and not result.text:  # type: ignore[union-attr]
            status = 429 if "exhausted" in (result.error or "") else 503  # type: ignore[union-attr]
            raise HTTPException(status_code=status, detail=result.error)  # type: ignore[union-attr]

        model_used = (key_data["model"] if key_data else None) or req.model or "unknown"
        provider_used = key_data["provider"] if key_data else "unknown"

        prompt_tokens = _estimate_tokens(req.messages)
        completion_tokens = result.tokens_used  # type: ignore[union-attr]
        total_tokens = prompt_tokens + completion_tokens

        return {
            "id": resp_id,
            "object": "chat.completion",
            "created": created,
            "model": model_used,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result.text}, "finish_reason": "stop"}],  # type: ignore[union-attr]
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "x_key_provider": provider_used,
        }

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        seen: set[str] = set()
        data = []
        for provider_name, cfg in configs.items():
            models = cfg.get("models", [])
            if isinstance(models, dict):
                models = [m for ms in models.values() for m in ms]
            default = cfg.get("default_model")
            if default and default not in models:
                models = [default, *list(models)]
            for m in models:
                if m and m not in seen:
                    seen.add(m)
                    data.append({"id": m, "object": "model", "owned_by": provider_name, "created": 0})
        return {"object": "list", "data": data}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        keys = store.get_all_keys()
        active = sum(1 for k in keys if k["is_active"])
        return {
            "status": "ok",
            "keys_total": len(keys),
            "keys_active": active,
            "capabilities": capabilities,
        }

    @app.get("/audit")
    async def audit_summary(days: int = 7) -> list[dict[str, Any]]:
        """Return aggregate audit summary."""
        return store.get_audit_summary(days=days)

    return app
