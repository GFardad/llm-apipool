from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def _create_health_router(store):
    router = APIRouter()
    @router.get("/health")
    async def health() -> dict[str, Any]:
        keys = store.get_all_keys()
        active = sum(1 for k in keys if k["is_active"])
        return {
            "status": "ok",
            "keys_total": len(keys),
            "keys_active": active,
        }

    @router.get("/audit")
    async def audit_summary(days: int = 7) -> list[dict[str, Any]]:
        return store.get_audit_summary(days=days)

    @router.post("/health/check")
    async def health_check_trigger() -> dict[str, Any]:
        from llm_keypool.core.health import check_all_keys

        await check_all_keys(store)
        return {"success": True, "message": "Health check triggered"}

    return router


__all__ = ["_create_health_router"]
