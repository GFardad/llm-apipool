"""Aggregated model catalog endpoint — backed by the ``models`` DB table.

Falls back to static ``providers.json`` when the database hasn't been
populated yet (e.g. before the first model sync).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from llm_keypool.core.model_db import get_models

_KEYPOOL_MODEL_ID = "LLM-Keypool"
_KEYPOOL_MODEL_OWNER = "llm-keypool"
_GATEWAY_IDS = [f"g{i}" for i in range(1, 20)]


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB model row to OpenAI-compatible model dict."""
    return {
        "id": row["model_id"],
        "object": "model",
        "owned_by": row.get("owner") or row["platform"],
        "created": 0,
        "provider": row["platform"],
        "context_window": row.get("context_window"),
        "max_input_tokens": row.get("max_input_tokens"),
        "max_output_tokens": row.get("max_output_tokens"),
        "supports_tools": bool(row.get("supports_tools", False)),
        "supports_vision": bool(row.get("supports_vision", False)),
        "supports_streaming": bool(row.get("supports_streaming", True)),
        "supports_function_calling": bool(row.get("supports_function_calling", False)),
        "is_free": bool(row.get("is_free", True)),
        "tier": row.get("tier", 4),
        "intelligence_rank": row.get("intelligence_rank", 999),
        "speed_rank": row.get("speed_rank", 999),
        "size_label": row.get("size_label", "Medium"),
        "limits": {
            "rpm": row.get("rpm_limit"),
            "rpd": row.get("rpd_limit"),
            "tpm": row.get("tpm_limit"),
            "tpd": row.get("tpd_limit"),
        },
    }


def _list_from_config(configs: dict[str, Any]) -> list[dict[str, Any]]:
    """Fallback: list models from ``providers.json`` config (no DB)."""
    seen: set[str] = set()
    data: list[dict[str, Any]] = [
        {"id": _KEYPOOL_MODEL_ID, "object": "model", "owned_by": _KEYPOOL_MODEL_OWNER, "created": 0},
    ]
    for gid in _GATEWAY_IDS:
        data.append({"id": gid, "object": "model", "owned_by": "llm-keypool", "created": 0})
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
    return data


def _create_models_router(configs, store: Any | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/models")
    async def list_models(
        provider: str | None = Query(None, description="Filter by provider"),
        tier: int | None = Query(None, description="Filter by quality tier (1-4)"),
        free_only: bool = Query(False, description="Only free-tier models"),
        min_context: int | None = Query(None, description="Minimum context window"),
        supports_tools: bool | None = Query(None, description="Filter for tool support"),
        supports_vision: bool | None = Query(None, description="Filter for vision support"),
        search: str | None = Query(None, description="Search model ID or display name"),
        sort_by: str = Query("tier", description="Sort field"),
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        enrich: bool = True,
    ) -> dict[str, Any]:
        data: list[dict[str, Any]] = []
        if store is not None:
            try:
                rows = get_models(
                    store._conn(),
                    provider=provider,
                    tier=tier,
                    free_only=free_only,
                    min_context=min_context,
                    supports_tools=supports_tools,
                    supports_vision=supports_vision,
                    search=search,
                    sort_by=sort_by,
                    limit=limit,
                    offset=offset,
                )
                if rows:
                    data = [_serialize(r) for r in rows]
            except Exception:
                pass
        if not data:
            data = _list_from_config(configs)

        # Always include the pool alias and gateway models at the front
        preamble = [
            {"id": _KEYPOOL_MODEL_ID, "object": "model", "owned_by": _KEYPOOL_MODEL_OWNER, "created": 0},
        ]
        for gid in _GATEWAY_IDS:
            preamble.append({"id": gid, "object": "model", "owned_by": "llm-keypool", "created": 0})

        seen = {e["id"] for e in preamble}
        deduped = preamble + [e for e in data if e["id"] not in seen]

        return {"object": "list", "data": deduped}

    return router


__all__ = ["_create_models_router"]
