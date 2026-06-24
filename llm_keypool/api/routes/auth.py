from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from llm_keypool.key_store import KeyStore


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str


def _create_auth_router(store: KeyStore) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    async def login(body: LoginRequest, response: Response) -> LoginResponse:
        # First user setup: create admin if no users exist
        with store._conn() as conn:
            existing = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if not existing:
            store.create_admin_user(body.email, body.password)
        token = store.authenticate(body.email, body.password)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        # Set session cookie
        response.set_cookie(
            key="session",
            value=token,
            max_age=2592000,  # 30 days
            httponly=True,
            samesite="lax",
            path="/",
        )
        return LoginResponse(token=token, email=body.email)

    @router.post("/logout")
    async def logout(request: Request, response: Response) -> dict[str, bool]:
        token = request.cookies.get("session")
        if token:
            store.logout(token)
        response.delete_cookie("session", path="/")
        return {"ok": True}

    @router.get("/me")
    async def me(request: Request) -> dict[str, Any]:
        token = request.cookies.get("session")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user_id = store.validate_session(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid session")
        return {"user_id": user_id, "authenticated": True}

    return router