from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

_STICKY_ENABLED = True
_HANDOFF_MODE = "auto"
_FALLBACK_CONFIG: dict[str, int] = {}


def _load_fallback_defaults() -> dict[str, int]:
    global _FALLBACK_CONFIG
    if not _FALLBACK_CONFIG:
        from llm_keypool.config.loader import load_settings
        fb = load_settings().fallback
        _FALLBACK_CONFIG = {
            "max_attempts_same_key": fb.max_attempts_same_key,
            "max_attempts_same_provider": fb.max_attempts_same_provider,
            "max_attempts_all_providers": fb.max_attempts_all_providers,
            "cooldown_on_failure_ms": fb.cooldown_on_failure_ms,
        }
    return _FALLBACK_CONFIG


class _SettingsRequest(BaseModel):
    strategy: str | None = None
    custom_weights: dict[str, float] | None = None


class _StickyRequest(BaseModel):
    sticky_enabled: bool | None = None


class _FallbackRequest(BaseModel):
    max_attempts_same_key: int | None = None
    max_attempts_same_provider: int | None = None
    max_attempts_all_providers: int | None = None
    cooldown_on_failure_ms: int | None = None


class _TierFallbackRequest(BaseModel):
    tier_fallback_enabled: bool | None = None


def _create_settings_router(store=None):
    router = APIRouter()
    @router.get("/api/settings/routing-strategy")
    async def get_routing_strategy() -> dict[str, Any]:
        from llm_keypool.core.router import get_routing_strategy

        return {"strategy": get_routing_strategy()}

    @router.put("/api/settings/routing-strategy")
    async def set_routing_strategy(req: _SettingsRequest) -> dict[str, Any]:
        from llm_keypool.core.router import set_routing_strategy

        if req.strategy:
            set_routing_strategy(req.strategy)
        return {"success": True}

    @router.get("/api/settings/sticky")
    async def get_sticky_settings() -> dict[str, Any]:
        from llm_keypool.core.sticky import is_sticky_enabled

        return {"sticky_enabled": is_sticky_enabled()}

    @router.put("/api/settings/sticky")
    async def set_sticky_settings(req: _StickyRequest) -> dict[str, Any]:
        from llm_keypool.core.sticky import set_sticky_enabled

        if req.sticky_enabled is not None:
            set_sticky_enabled(req.sticky_enabled)
        return {"success": True}

    @router.get("/api/settings/handoff")
    async def get_handoff_settings() -> dict[str, Any]:
        from llm_keypool.core.handoff import get_handoff_mode

        return {"mode": get_handoff_mode()}

    @router.get("/api/settings/fallback")
    async def get_fallback_settings() -> dict[str, Any]:
        return _load_fallback_defaults()

    @router.put("/api/settings/fallback")
    async def set_fallback_settings(req: _FallbackRequest) -> dict[str, Any]:
        cfg = _load_fallback_defaults()
        if req.max_attempts_same_key is not None:
            cfg["max_attempts_same_key"] = req.max_attempts_same_key
        if req.max_attempts_same_provider is not None:
            cfg["max_attempts_same_provider"] = req.max_attempts_same_provider
        if req.max_attempts_all_providers is not None:
            cfg["max_attempts_all_providers"] = req.max_attempts_all_providers
        if req.cooldown_on_failure_ms is not None:
            cfg["cooldown_on_failure_ms"] = req.cooldown_on_failure_ms
        return {"success": True}

    @router.get("/api/settings/tier-fallback")
    async def get_tier_fallback() -> dict[str, Any]:
        from llm_keypool.core.tier_fallback import is_tier_fallback_enabled
        return {"tier_fallback_enabled": is_tier_fallback_enabled()}

    @router.put("/api/settings/tier-fallback")
    async def set_tier_fallback(req: _TierFallbackRequest) -> dict[str, Any]:
        from llm_keypool.core.tier_fallback import set_tier_fallback_enabled
        if req.tier_fallback_enabled is not None:
            set_tier_fallback_enabled(req.tier_fallback_enabled)
        return {"success": True}

    return router


__all__ = ["_create_settings_router"]
