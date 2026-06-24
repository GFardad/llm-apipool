"""FastAPI app factory — composes all route modules into a single app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from llm_keypool.api.routes.analytics import _create_analytics_router
from llm_keypool.api.routes.auth import _create_auth_router
from llm_keypool.api.routes.chat import _create_chat_router
from llm_keypool.api.routes.embeddings import _create_embeddings_router
from llm_keypool.api.routes.health import _create_health_router
from llm_keypool.api.routes.keys import _create_keys_router
from llm_keypool.api.routes.models import _create_models_router
from llm_keypool.api.routes.settings import _create_settings_router
from llm_keypool.api.routes.tiers import _create_tiers_router
from llm_keypool.key_store import KeyStore
from llm_keypool.rotator import Rotator


def _load_provider_configs() -> dict[str, Any]:
    config_path = Path(__file__).parent.parent / "config" / "providers.json"
    with config_path.open() as f:
        return json.load(f)["providers"]


def make_app(
    capabilities: list[str] | None = None,
    rotate_every: int = 5,
    quality_tier: int = 1,
    max_fallback_tier: int = 4,
    *,
    _configs: dict[str, Any] | None = None,
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
    _configs:
        Optional pre-loaded provider configs (for testing).
    """
    if capabilities is None:
        capabilities = ["general_purpose"]

    store = KeyStore()
    configs = _configs if _configs is not None else _load_provider_configs()
    rotator = Rotator(
        store,
        configs,
        rotate_every=rotate_every,
        quality_tier=quality_tier,
        max_fallback_tier=max_fallback_tier,
    )

    # Force all chat-completion routing to opencode_zen / deepseek-v4-flash-free
    rotator.set_force_provider("opencode_zen", "deepseek-v4-flash-free")

    app = FastAPI(title="llm-keypool proxy", version="2.1")

    # Comprehensive logging — every request's headers, body, status, and timing
    from llm_keypool.api.middleware.logging import add_logging_middleware
    add_logging_middleware(app)

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": f"{type(exc).__name__}: {str(exc)[:300]}", "type": "server_error", "code": "500"}},
        )

    # Auth middleware - protect all /api/* routes except /api/auth/*
    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        path = request.url.path
        # Skip auth for auth routes and non-API routes
        if path.startswith("/api/auth") or not path.startswith("/api"):
            return await call_next(request)
        # Check session cookie
        token = request.cookies.get("session")
        if not token:
            return HTMLResponse(
                json.dumps({"error": "Authentication required"}),
                status_code=401,
                media_type="application/json",
            )
        user_id = store.validate_session(token)
        if not user_id:
            return HTMLResponse(
                json.dumps({"error": "Invalid or expired session"}),
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)

    # Compose all route modules
    app.include_router(_create_auth_router(store))
    app.include_router(_create_chat_router(store, rotator, configs, capabilities))
    app.include_router(_create_models_router(configs, store=store))
    app.include_router(_create_health_router(store))
    app.include_router(_create_keys_router(store, configs))
    app.include_router(_create_analytics_router(store))
    app.include_router(_create_settings_router(store))
    app.include_router(_create_tiers_router())
    app.include_router(_create_embeddings_router(store))

    # Serve React dashboard from web/dist (built frontend) via catch-all route
    # Mount approach (app.mount) fails for sub-paths — empty mount path doesn't
    # match sub-routes in Starlette routing.
    web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    web_index = web_dist / "index.html"

    if web_index.exists():
        index_html = web_index.read_text()

        @app.get("/{path:path}")
        async def _spa_fallback(request: Request, path: str) -> HTMLResponse:
            # Check if file exists in web_dist (for assets)
            file_path = web_dist / path
            if file_path.exists() and file_path.is_file():
                content = file_path.read_bytes()
                # Determine content type
                if path.endswith(".js"):
                    return HTMLResponse(content, media_type="application/javascript")
                elif path.endswith(".css"):
                    return HTMLResponse(content, media_type="text/css")
                elif path.endswith(".html"):
                    return HTMLResponse(content, media_type="text/html")
                else:
                    return HTMLResponse(content)
            # Let API routes handle their own paths; catch everything else for SPA
            return HTMLResponse(index_html)

        # Also serve root explicitly
        @app.get("/")
        async def _root() -> HTMLResponse:
            return HTMLResponse(index_html)
    else:
        @app.get("/")
        async def _root_fallback() -> dict[str, Any]:
            return {
                "name": "llm-keypool",
                "version": "2.1",
                "note": "Frontend not built — run `cd frontend && npm run build`",
            }

    return app


__all__ = ["make_app"]
