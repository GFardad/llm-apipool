from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


class _KeyUpdate(BaseModel):
    model: str | None = None
    api_key: str | None = None
    capabilities: list[str] | None = None
    context_size: int | None = None
    accuracy_score: int | None = None
    speed_score: int | None = None
    reliability_score: int | None = None
    group_name: str | None = None
    is_sticky_enabled: bool | None = None
    sticky_ttl_hours: int | None = None
    priority: int | None = None


class _KeyCreate(BaseModel):
    provider: str
    api_key: str
    capabilities: list[str] | None = None
    model: str | None = None
    base_url_override: str | None = None
    context_size: int | None = None
    accuracy_score: int = 50
    speed_score: int = 50
    reliability_score: int = 50
    group_name: str = "default"


def _create_keys_router(store, configs):
    router = APIRouter()
    @router.get("/api/keys")
    async def list_keys(active_only: bool = False) -> list[dict[str, Any]]:
        keys = store.get_all_keys()
        if active_only:
            keys = [k for k in keys if k["is_active"]]
        return keys

    @router.post("/api/keys")
    async def create_key(data: _KeyCreate) -> dict[str, Any]:
        result = store.register_key(
            provider=data.provider,
            api_key=data.api_key,
            capabilities=data.capabilities,
            model=data.model,
            base_url_override=data.base_url_override,
            context_size=data.context_size,
            accuracy_score=data.accuracy_score,
            speed_score=data.speed_score,
            reliability_score=data.reliability_score,
            group_name=data.group_name,
        )
        return result

    @router.patch("/api/keys/{key_id}")
    async def update_key(key_id: int, data: _KeyUpdate) -> dict[str, Any]:
        if data.model is not None or data.api_key is not None:
            store.update_key(key_id, model=data.model, api_key=data.api_key)
        if any(s is not None for s in [data.accuracy_score, data.speed_score, data.reliability_score]):
            store.update_key_scores(
                key_id,
                accuracy_score=data.accuracy_score,
                speed_score=data.speed_score,
                reliability_score=data.reliability_score,
            )
        if data.group_name is not None:
            store.update_key_group(key_id, data.group_name)
        if data.is_sticky_enabled is not None:
            store.update_key_sticky(key_id, data.is_sticky_enabled, data.sticky_ttl_hours or 1)
        if data.priority is not None:
            store.update_priority(key_id, data.priority)
        return {"success": True, "message": f"Key {key_id} updated"}

    @router.patch("/api/keys/{key_id}/priority")
    async def update_priority_endpoint(key_id: int, priority: int) -> dict[str, Any]:
        store.update_priority(key_id, priority)
        return {"success": True, "message": f"Key {key_id} priority set to {priority}"}

    @router.delete("/api/keys/{key_id}")
    async def delete_key_endpoint(key_id: int) -> dict[str, Any]:
        deleted = store.delete_key(key_id)
        if deleted:
            return {"success": True, "message": f"Key {key_id} deleted"}
        return {"success": False, "message": f"Key {key_id} not found"}

    @router.post("/api/keys/{key_id}/activate")
    async def activate_key_endpoint(key_id: int) -> dict[str, Any]:
        store.activate_key(key_id)
        return {"success": True, "message": f"Key {key_id} activated"}

    @router.post("/api/keys/{key_id}/deactivate")
    async def deactivate_key_endpoint(key_id: int) -> dict[str, Any]:
        store.deactivate_key(key_id)
        return {"success": True, "message": f"Key {key_id} deactivated"}

    @router.post("/api/keys/{key_id}/clear-cooldown")
    async def clear_cooldown_endpoint(key_id: int) -> dict[str, Any]:
        store.clear_cooldown(key_id)
        return {"success": True, "message": f"Cooldown cleared for key {key_id}"}

    @router.get("/api/providers")
    async def list_providers() -> dict[str, Any]:
        return {"providers": sorted(configs.keys())}

    @router.post("/api/test-key")
    async def test_key(provider: str = "", api_key: str = "") -> dict[str, Any]:
        import asyncio
        from llm_keypool.key_checker import check_key_against_provider

        if not provider or not api_key:
            return {"healthy": False, "detail": "Provider and API key required"}
        async with asyncio.timeout(10):
            prov, success, detail = await check_key_against_provider(provider, api_key)
        return {"healthy": success, "detail": detail}

    return router


__all__ = ["_create_keys_router"]
