"""Simple API authentication middleware.

Supports optional API key validation via X-API-Key header.
When LLM_KEYPOOL_API_KEY env var is set, all requests must include it.
When unset, all requests pass through (open access).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


def _get_required_key() -> str | None:
    """Return the configured API key, or None if auth is disabled."""
    return os.environ.get("LLM_KEYPOOL_API_KEY") or None


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key validation middleware."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        required_key = _get_required_key()
        if required_key:
            provided = request.headers.get("X-API-Key", "")
            if not provided or provided != required_key:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or missing X-API-Key header",
                )
        return await call_next(request)


def add_auth_middleware(app: Any) -> None:
    """Conditionally add auth middleware if LLM_KEYPOOL_API_KEY is set."""
    if _get_required_key():
        app.add_middleware(APIKeyMiddleware)
