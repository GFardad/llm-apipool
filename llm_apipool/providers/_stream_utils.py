"""Shared SSE streaming chunk builders—extracted from 4× identical copies across provider modules."""

from __future__ import annotations

import uuid
from typing import Any


def make_chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _normalize_delta_content(
    content: Any,  # noqa: ANN401
) -> str | None:
    """Normalize ``delta.content`` to ``str | None``.

    Some providers (notably multi-modal ones) emit ``delta.content`` as a list
    of content parts ``[{"type": "text", "text": "hello"}]`` instead of a plain
    string ``"hello"``.  OpenAI clients expect a string; normalise here.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("value") or ""
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts) if parts else None
    return str(content) if content else None


def build_chunk(
    chunk_id: str,
    created: int,
    model: str,
    delta_content: str | None = None,
    delta_role: str | None = None,
    finish_reason: str | None = None,
    index: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
    }
    if delta_content is not None or delta_role is not None or finish_reason is not None:
        delta: dict[str, Any] = {}
        if delta_role is not None:
            delta["role"] = delta_role
        if delta_content is not None:
            delta["content"] = delta_content
        chunk["choices"] = [
            {
                "index": index,
                "delta": delta,
                "finish_reason": finish_reason,
            },
        ]
    chunk.update(extra)
    return chunk
