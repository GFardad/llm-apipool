from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_MODEL_QUALITY_PATH = _CONFIG_DIR / "model_quality.json"

_lock = threading.Lock()


def _load_tiers() -> dict[str, list[str]]:
    with _MODEL_QUALITY_PATH.open() as f:
        return json.load(f)


def _save_tiers(data: dict[str, list[str]]) -> None:
    with _MODEL_QUALITY_PATH.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


class _TiersResponse(BaseModel):
    tiers: dict[str, list[str]]


class _MoveModelRequest(BaseModel):
    model: str
    from_tier: str
    to_tier: str


def _create_tiers_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/tiers")
    async def get_tiers() -> _TiersResponse:
        with _lock:
            tiers = _load_tiers()
        return _TiersResponse(tiers=tiers)

    @router.put("/api/tiers")
    async def update_tiers(req: _TiersResponse) -> dict[str, Any]:
        with _lock:
            current = _load_tiers()
            for tier_key, models in req.tiers.items():
                if tier_key in current:
                    current[tier_key] = models
            _save_tiers(current)
        return {"success": True, "message": "Tiers updated"}

    @router.post("/api/tiers/move-model")
    async def move_model(req: _MoveModelRequest) -> dict[str, Any]:
        with _lock:
            tiers = _load_tiers()
            if req.from_tier not in tiers or req.to_tier not in tiers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid tier keys: {req.from_tier}, {req.to_tier}. Valid: {list(tiers.keys())}",
                )
            if req.model not in tiers[req.from_tier]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{req.model}' not found in tier '{req.from_tier}'",
                )
            tiers[req.from_tier].remove(req.model)
            if req.model not in tiers[req.to_tier]:
                tiers[req.to_tier].append(req.model)
            _save_tiers(tiers)
        return {"success": True, "message": f"Moved '{req.model}' from {req.from_tier} to {req.to_tier}"}

    return router


__all__ = ["_create_tiers_router"]
