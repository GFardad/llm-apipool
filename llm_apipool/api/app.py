"""FastAPI app factory — composes all route modules into a single app."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from llm_apipool.api.middleware.auth import add_proxy_auth_middleware
from llm_apipool.api.middleware.logging import add_logging_middleware
from llm_apipool.api.middleware.security import add_security_headers_middleware
from llm_apipool.api.routes.analytics import _create_analytics_router
from llm_apipool.api.routes.anthropic import _create_anthropic_router

from llm_apipool.api.routes.chat import _create_chat_router
from llm_apipool.api.routes.effort import _create_effort_router
from llm_apipool.api.routes.embeddings import _create_embeddings_router
from llm_apipool.api.routes.freemodels import _create_freemodels_router
from llm_apipool.api.routes.health import _create_health_router
from llm_apipool.api.routes.keys import _create_keys_router
from llm_apipool.api.routes.logs import _create_logs_router
from llm_apipool.api.routes.media import _create_media_router
from llm_apipool.api.routes.models import _create_models_router
from llm_apipool.api.routes.settings import _create_settings_router
from llm_apipool.api.routes.benchmark import _create_benchmark_router
from llm_apipool.api.routes.bulk_import import _create_bulk_import_router
from llm_apipool.api.routes.tiers import _create_tiers_router
from llm_apipool.core.health_check import HealthCheckService
from llm_apipool.core.model_sync_service import ModelSyncService
from llm_apipool.core.ratelimiter import add_rate_limit_middleware
from llm_apipool.key_store import KeyStore
from llm_apipool.rotator import Rotator


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
        Default capabilities to use when the ``X-Apipool-Capabilities`` header
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

    # Optional: force all chat-completion routing to a specific provider
    # Set LLM_APIPOOL_FORCE_PROVIDER=provider_name and LLM_APIPOOL_FORCE_MODEL=model_id
    _forced_provider = os.environ.get("LLM_APIPOOL_FORCE_PROVIDER")
    if _forced_provider:
        _forced_model = os.environ.get("LLM_APIPOOL_FORCE_MODEL")
        rotator.set_force_provider(_forced_provider, _forced_model)

    # Restore dashboard settings from DB on startup
    from llm_apipool.api.routes.settings import restore_settings_from_db

    restore_settings_from_db(store, rotator)

    # Health check service — periodic background key probing
    _health_check_interval = int(
        os.environ.get("LLM_APIPOOL_HEALTH_CHECK_INTERVAL", "300")
    )
    _health_service: HealthCheckService | None = None
    if _health_check_interval > 0:
        _health_service = HealthCheckService(
            store, interval_seconds=_health_check_interval
        )

    # Model sync service — periodic background model catalogue refresh
    _model_sync_interval = int(
        os.environ.get("LLM_APIPOOL_MODEL_SYNC_INTERVAL", "3600")
    )
    _model_sync_service: ModelSyncService | None = None
    if _model_sync_interval > 0:
        _model_sync_service = ModelSyncService(
            store,
            configs,
            interval_seconds=_model_sync_interval,
        )

    _background_tasks: list[asyncio.Task[None]] = []

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Startup: launch background services.  Shutdown: cancel tasks."""
        if _health_service:
            task = asyncio.create_task(_health_service.run(), name="health-check")
            _background_tasks.append(task)
        if _model_sync_service:
            task = asyncio.create_task(_model_sync_service.run(), name="model-sync")
            _background_tasks.append(task)
        yield
        if _health_service:
            _health_service.stop()
        if _model_sync_service:
            _model_sync_service.stop()
        for task in _background_tasks:
            task.cancel()
        if _background_tasks:
            await asyncio.gather(*_background_tasks, return_exceptions=True)
        _background_tasks.clear()

    app = FastAPI(title="llm-apipool proxy", version="1.0.0", lifespan=_lifespan)

    # Compose all route modules
    app.include_router(_create_anthropic_router(store, rotator, configs, capabilities))
    app.include_router(_create_chat_router(store, rotator, configs, capabilities))
    app.include_router(
        _create_models_router(
            configs,
            store=store,
            sync_fn=_model_sync_service._sync_all if _model_sync_service else None,
        )
    )
    app.include_router(_create_health_router(store))
    app.include_router(_create_keys_router(store, configs, rotator))
    app.include_router(_create_logs_router(store))
    app.include_router(_create_analytics_router(store))
    app.include_router(_create_settings_router(store, rotator))
    app.include_router(_create_tiers_router())
    app.include_router(_create_effort_router())
    app.include_router(_create_bulk_import_router(store, configs))
    app.include_router(_create_embeddings_router(store))
    app.include_router(_create_media_router(store, rotator, configs, capabilities))
    app.include_router(_create_freemodels_router(store=store))
    app.include_router(_create_benchmark_router(store=store))

    # Serve React dashboard from web/dist (built frontend) via catch-all route
    # Mount approach (app.mount) fails for sub-paths — empty mount path doesn't
    # match sub-routes in Starlette routing.
    web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    web_index = web_dist / "index.html"

    if web_index.exists():
        from fastapi.responses import Response

        def _read_index() -> bytes:
            """Read index.html from disk on every call so asset hashes are
            always fresh after a rebuild — no server restart required."""
            try:
                return web_index.read_bytes()
            except OSError:
                return b"<html><body><p>App not built</p></body></html>"

        @app.get("/{path:path}")
        async def _spa_fallback(request: Request, path: str) -> Response:
            file_path = web_dist / path
            if file_path.exists() and file_path.is_file():
                content = file_path.read_bytes()
                mime_type, _ = mimetypes.guess_type(str(file_path))
                return Response(
                    content, media_type=mime_type or "application/octet-stream"
                )

            # Return 404 for missing assets (e.g. stale cached index.html with
            # old hash filenames after a rebuild).  Must set media_type so the
            # browser doesn't choke on empty Content-Type + nosniff.
            if path.startswith("assets/") or path.endswith(
                (".js", ".css", ".woff", ".woff2")
            ):
                return Response(
                    b'{"error":"not_found"}',
                    status_code=404,
                    media_type="application/json",
                    headers={"Cache-Control": "no-store"},
                )

            # SPA fallback: read fresh from disk so rebuilt asset hashes
            # are always served — no server restart needed.
            html = _read_index()
            return Response(
                html,
                media_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        # Also serve root explicitly
        @app.get("/")
        async def _root() -> Response:
            html = _read_index()
            return Response(
                html,
                media_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    else:

        @app.get("/")
        async def _root_fallback() -> dict[str, Any]:
            return {
                "name": "llm-apipool",
                "version": "1.0.0",
                "note": "Frontend not built — run `cd frontend && npm run build`",
            }

    # ── Middleware ─────────────────────────────────────────────────────────
    # CORS — allow all origins for dashboard access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_security_headers_middleware(app)
    add_proxy_auth_middleware(app)
    add_rate_limit_middleware(app, rate=10.0, burst=20)
    add_logging_middleware(app)

    return app


__all__ = ["make_app"]
