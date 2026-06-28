from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from llm_apipool.rotator import MIN_QUALITY_TIER, MAX_QUALITY_TIER

_STICKY_ENABLED = True
_HANDOFF_MODE = "auto"
_FALLBACK_CONFIG: dict[str, int] = {}


def _load_fallback_defaults() -> dict[str, int]:
    global _FALLBACK_CONFIG
    if not _FALLBACK_CONFIG:
        from llm_apipool.config.loader import load_settings

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
    sticky_ttl_ms: int | None = None
    max_sticky_entries: int | None = None


class _FallbackRequest(BaseModel):
    max_attempts_same_key: int | None = None
    max_attempts_same_provider: int | None = None
    max_attempts_all_providers: int | None = None
    cooldown_on_failure_ms: int | None = None


class _TierFallbackRequest(BaseModel):
    tier_fallback_enabled: bool | None = None


class _HandoffRequest(BaseModel):
    mode: str | None = None


class _TierSettingsRequest(BaseModel):
    quality_tier: int | None = None
    max_fallback_tier: int | None = None


class _AffinityRequest(BaseModel):
    affinity_enabled: bool | None = None


class _RoutingOverrideRequest(BaseModel):
    models: list[str] = []


class _RoutingOverrideClearRequest(BaseModel):
    pass


class _SaveAllRequest(BaseModel):
    strategy: str | None = None
    custom_weights: dict[str, float] | None = None
    sticky_enabled: bool | None = None
    sticky_ttl_ms: int | None = None
    max_sticky_entries: int | None = None
    handoff_mode: str | None = None
    quality_tier: int | None = None
    max_fallback_tier: int | None = None
    tier_fallback_enabled: bool | None = None
    affinity_enabled: bool | None = None
    fallback: dict[str, int] | None = None
    forced_models: list[str] | None = None


def _create_settings_router(store: Any = None, rotator: Any = None) -> APIRouter:
    router = APIRouter()

    def _get_rotator() -> Any:
        return rotator

    @router.get("/api/settings/routing-strategy")
    async def get_routing_strategy() -> dict[str, Any]:
        from llm_apipool.core.router import get_routing_strategy

        return {"strategy": get_routing_strategy()}

    @router.put("/api/settings/routing-strategy")
    async def set_routing_strategy(req: _SettingsRequest) -> dict[str, Any]:
        from llm_apipool.core.router import set_routing_strategy

        if req.strategy:
            set_routing_strategy(req.strategy)
        return {"success": True}

    @router.get("/api/settings/sticky")
    async def get_sticky_settings() -> dict[str, Any]:
        from llm_apipool.core.sticky import (
            is_sticky_enabled,
            get_sticky_ttl_ms,
            get_max_sticky_entries,
            get_all_sessions,
        )  # noqa: F811

        return {
            "sticky_enabled": is_sticky_enabled(),
            "sticky_ttl_ms": get_sticky_ttl_ms(),
            "max_sticky_entries": get_max_sticky_entries(),
            "active_sessions": len(get_all_sessions()),
        }

    @router.put("/api/settings/sticky")
    async def set_sticky_settings(req: _StickyRequest) -> dict[str, Any]:
        from llm_apipool.core.sticky import (
            set_sticky_enabled,
            set_sticky_ttl_ms,
            set_max_sticky_entries,
        )

        if req.sticky_enabled is not None:
            set_sticky_enabled(req.sticky_enabled)
        if req.sticky_ttl_ms is not None:
            try:
                set_sticky_ttl_ms(req.sticky_ttl_ms)
            except ValueError as e:
                from llm_apipool.api.errors import INVALID_REQUEST_ERROR, error_response

                return error_response(400, str(e), INVALID_REQUEST_ERROR)
        if req.max_sticky_entries is not None:
            try:
                set_max_sticky_entries(req.max_sticky_entries)
            except ValueError as e:
                from llm_apipool.api.errors import INVALID_REQUEST_ERROR, error_response

                return error_response(400, str(e), INVALID_REQUEST_ERROR)
        return {"success": True}

    @router.get("/api/settings/handoff")
    async def get_handoff_settings() -> dict[str, Any]:
        from llm_apipool.core.handoff import get_handoff_mode

        return {"mode": get_handoff_mode()}

    @router.put("/api/settings/handoff")
    async def set_handoff_settings(req: _HandoffRequest) -> dict[str, Any]:
        from llm_apipool.core.handoff import set_handoff_mode

        if req.mode is not None:
            try:
                set_handoff_mode(req.mode)
            except ValueError as e:
                from llm_apipool.api.errors import INVALID_REQUEST_ERROR, error_response

                return error_response(400, str(e), INVALID_REQUEST_ERROR)
        return {"success": True}

    @router.get("/api/settings/tier-settings")
    async def get_tier_settings() -> dict[str, Any]:
        r = _get_rotator()
        if r is None:
            return {"quality_tier": 1, "max_fallback_tier": 4}
        return {
            "quality_tier": r.get_quality_tier(),
            "max_fallback_tier": r.get_max_fallback_tier(),
            "min_tier": MIN_QUALITY_TIER,
            "max_tier": MAX_QUALITY_TIER,
        }

    @router.put("/api/settings/tier-settings")
    async def set_tier_settings(req: _TierSettingsRequest) -> dict[str, Any]:
        r = _get_rotator()
        if r is None:
            return {"success": False, "error": "Rotator not available"}
        if req.quality_tier is not None:
            try:
                r.set_quality_tier(req.quality_tier)
            except ValueError as e:
                from llm_apipool.api.errors import INVALID_REQUEST_ERROR, error_response

                return error_response(400, str(e), INVALID_REQUEST_ERROR)
        if req.max_fallback_tier is not None:
            try:
                r.set_max_fallback_tier(req.max_fallback_tier)
            except ValueError as e:
                from llm_apipool.api.errors import INVALID_REQUEST_ERROR, error_response

                return error_response(400, str(e), INVALID_REQUEST_ERROR)
        return {"success": True}

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
        from llm_apipool.core.tier_fallback import is_tier_fallback_enabled

        return {"tier_fallback_enabled": is_tier_fallback_enabled()}

    @router.put("/api/settings/tier-fallback")
    async def set_tier_fallback(req: _TierFallbackRequest) -> dict[str, Any]:
        from llm_apipool.core.tier_fallback import set_tier_fallback_enabled

        if req.tier_fallback_enabled is not None:
            set_tier_fallback_enabled(req.tier_fallback_enabled)
        return {"success": True}

    @router.get("/api/settings/affinity")
    async def get_affinity_settings() -> dict[str, Any]:
        from llm_apipool.core.affinity import is_affinity_enabled, get_state_snapshot

        snap = get_state_snapshot()
        return {
            "affinity_enabled": is_affinity_enabled(),
            "available_slots": snap["available_slots"],
            "total_slots": snap["total_slots"],
            "busy": snap["busy"],
            "semi_busy": snap["semi_busy"],
            "pinned_uids": snap["pinned_uids"],
        }

    @router.put("/api/settings/affinity")
    async def set_affinity_settings(req: _AffinityRequest) -> dict[str, Any]:
        from llm_apipool.core.affinity import set_affinity_enabled

        if req.affinity_enabled is not None:
            # Mutual exclusion: disabling sticky when enabling affinity
            if req.affinity_enabled:
                from llm_apipool.core.sticky import set_sticky_enabled

                set_sticky_enabled(False)
            set_affinity_enabled(req.affinity_enabled)
        return {"success": True}

    @router.get("/api/settings/routing-override")
    async def get_routing_override() -> dict[str, Any]:
        r = _get_rotator()
        if r is None:
            return {"models": [], "override_active": False}
        models = r.forced_models
        return {
            "models": models,
            "override_active": len(models) > 0,
        }

    @router.post("/api/settings/routing-override")
    async def set_routing_override(req: _RoutingOverrideRequest) -> dict[str, Any]:
        r = _get_rotator()
        if r is None:
            return {"success": False, "error": "Rotator not available"}
        r.set_forced_models(req.models)
        return {"success": True, "models": req.models}

    @router.delete("/api/settings/routing-override")
    async def clear_routing_override() -> dict[str, Any]:
        r = _get_rotator()
        if r is None:
            return {"success": False, "error": "Rotator not available"}
        r.clear_forced_models()
        return {"success": True}

    @router.post("/api/settings/save-all")
    async def save_all_settings(req: _SaveAllRequest) -> dict[str, Any]:
        r = _get_rotator()
        errors: list[str] = []

        if req.strategy is not None:
            from llm_apipool.core.router import set_routing_strategy, set_custom_weights

            try:
                set_routing_strategy(req.strategy)
            except ValueError as e:
                errors.append(f"strategy: {e}")

        if req.custom_weights is not None:
            from llm_apipool.core.router import set_custom_weights

            try:
                set_custom_weights(req.custom_weights)
            except Exception as e:
                errors.append(f"custom_weights: {e}")

        if req.sticky_enabled is not None:
            from llm_apipool.core.sticky import set_sticky_enabled

            try:
                set_sticky_enabled(req.sticky_enabled)
            except Exception as e:
                errors.append(f"sticky_enabled: {e}")

        if req.sticky_ttl_ms is not None:
            from llm_apipool.core.sticky import set_sticky_ttl_ms

            try:
                set_sticky_ttl_ms(req.sticky_ttl_ms)
            except ValueError as e:
                errors.append(f"sticky_ttl_ms: {e}")

        if req.max_sticky_entries is not None:
            from llm_apipool.core.sticky import set_max_sticky_entries

            try:
                set_max_sticky_entries(req.max_sticky_entries)
            except ValueError as e:
                errors.append(f"max_sticky_entries: {e}")

        if req.handoff_mode is not None:
            from llm_apipool.core.handoff import set_handoff_mode

            try:
                set_handoff_mode(req.handoff_mode)
            except ValueError as e:
                errors.append(f"handoff_mode: {e}")

        if req.tier_fallback_enabled is not None:
            from llm_apipool.core.tier_fallback import set_tier_fallback_enabled

            try:
                set_tier_fallback_enabled(req.tier_fallback_enabled)
            except Exception as e:
                errors.append(f"tier_fallback_enabled: {e}")

        if req.affinity_enabled is not None:
            from llm_apipool.core.affinity import set_affinity_enabled

            try:
                if req.affinity_enabled:
                    from llm_apipool.core.sticky import set_sticky_enabled

                    set_sticky_enabled(False)
                set_affinity_enabled(req.affinity_enabled)
            except Exception as e:
                errors.append(f"affinity_enabled: {e}")

        if r is not None:
            if req.quality_tier is not None:
                try:
                    r.set_quality_tier(req.quality_tier)
                except ValueError as e:
                    errors.append(f"quality_tier: {e}")
            if req.max_fallback_tier is not None:
                try:
                    r.set_max_fallback_tier(req.max_fallback_tier)
                except ValueError as e:
                    errors.append(f"max_fallback_tier: {e}")
            if req.forced_models is not None:
                try:
                    r.set_forced_models(req.forced_models)
                except Exception as e:
                    errors.append(f"forced_models: {e}")

        if req.fallback is not None:
            cfg = _load_fallback_defaults()
            for k, v in req.fallback.items():
                if k in cfg:
                    try:
                        cfg[k] = int(v)
                    except (ValueError, TypeError) as e:
                        errors.append(f"fallback.{k}: {e}")

        # Persist all provided values to DB
        if store is not None:
            mapping = {
                "strategy": req.strategy,
                "custom_weights": req.custom_weights,
                "sticky_enabled": req.sticky_enabled,
                "sticky_ttl_ms": req.sticky_ttl_ms,
                "max_sticky_entries": req.max_sticky_entries,
                "handoff_mode": req.handoff_mode,
                "quality_tier": req.quality_tier,
                "max_fallback_tier": req.max_fallback_tier,
                "tier_fallback_enabled": req.tier_fallback_enabled,
                "affinity_enabled": req.affinity_enabled,
                "fallback": req.fallback,
                "forced_models": req.forced_models,
            }
            for sk, sv in mapping.items():
                if sv is not None:
                    store.save_setting(sk, sv)

        return {"success": True, "errors": errors}

    return router


def restore_settings_from_db(store: Any, rotator: Any) -> None:
    """Load all persisted settings from DB and re-apply them to in-memory state."""
    if store is None:
        return
    settings = store.load_all_settings()

    try:
        val = settings.get("strategy")
        if val is not None:
            from llm_apipool.core.router import set_routing_strategy

            set_routing_strategy(str(val))
    except Exception:
        pass

    try:
        val = settings.get("custom_weights")
        if val is not None and isinstance(val, dict):
            from llm_apipool.core.router import set_custom_weights

            set_custom_weights(val)
    except Exception:
        pass

    try:
        val = settings.get("sticky_enabled")
        if val is not None:
            from llm_apipool.core.sticky import set_sticky_enabled

            set_sticky_enabled(bool(val))
    except Exception:
        pass

    try:
        val = settings.get("sticky_ttl_ms")
        if val is not None:
            from llm_apipool.core.sticky import set_sticky_ttl_ms

            set_sticky_ttl_ms(int(val))
    except Exception:
        pass

    try:
        val = settings.get("max_sticky_entries")
        if val is not None:
            from llm_apipool.core.sticky import set_max_sticky_entries

            set_max_sticky_entries(int(val))
    except Exception:
        pass

    try:
        val = settings.get("handoff_mode")
        if val is not None:
            from llm_apipool.core.handoff import set_handoff_mode

            set_handoff_mode(str(val))
    except Exception:
        pass

    try:
        val = settings.get("tier_fallback_enabled")
        if val is not None:
            from llm_apipool.core.tier_fallback import set_tier_fallback_enabled

            set_tier_fallback_enabled(bool(val))
    except Exception:
        pass

    try:
        val = settings.get("affinity_enabled")
        if val is not None:
            from llm_apipool.core.affinity import set_affinity_enabled

            set_affinity_enabled(bool(val))
    except Exception:
        pass

    try:
        val = settings.get("fallback")
        if val is not None and isinstance(val, dict):
            _load_fallback_defaults().update(val)
    except Exception:
        pass

    if rotator is not None:
        try:
            val = settings.get("quality_tier")
            if val is not None:
                rotator.set_quality_tier(int(val))
        except Exception:
            pass
        try:
            val = settings.get("max_fallback_tier")
            if val is not None:
                rotator.set_max_fallback_tier(int(val))
        except Exception:
            pass
        try:
            val = settings.get("forced_models")
            if val is not None and isinstance(val, list):
                rotator.set_forced_models(val)
        except Exception:
            pass


__all__ = ["_create_settings_router", "restore_settings_from_db"]
