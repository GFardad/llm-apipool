"""Prompt caching layer — intercepts requests before dispatch.

Cache identical requests (model + messages + params) to reduce latency
and conserve API rate limits.  Streaming requests are never cached.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any


_CACHE_ENABLED = True
_CACHE_TTL = 60
_CACHE_MAX_ENTRIES = 1000


def is_cache_enabled() -> bool:
    return _CACHE_ENABLED


def set_cache_enabled(val: bool) -> None:
    global _CACHE_ENABLED  # noqa: PLW0603
    _CACHE_ENABLED = val


def get_cache_ttl() -> int:
    return _CACHE_TTL


def set_cache_ttl(val: int) -> None:
    global _CACHE_TTL  # noqa: PLW0603
    _CACHE_TTL = val


def get_cache_max_entries() -> int:
    return _CACHE_MAX_ENTRIES


def set_cache_max_entries(val: int) -> None:
    global _CACHE_MAX_ENTRIES  # noqa: PLW0603
    _CACHE_MAX_ENTRIES = val


class CacheEntry:
    """A single cache entry with expiry and LRU tracking."""

    __slots__ = ("response", "expires_at", "accessed_at")

    def __init__(self, response: dict[str, Any], ttl: int) -> None:
        now = time.monotonic()
        self.response: dict[str, Any] = response
        self.expires_at: float = now + ttl
        self.accessed_at: float = now


class PromptCache:
    """In-memory request cache with TTL expiry and LRU eviction.

    Cache key is a SHA-256 of the canonical JSON representation of
    ``(model, messages, params)``.  The ``stream`` parameter is excluded
    from the key since streaming is never cached.
    """

    def __init__(
        self,
        default_ttl: int = 60,
        max_entries: int = 1000,
    ) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(
        model: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> str:
        """Build a deterministic SHA-256 cache key.

        The ``stream`` key is stripped from *params* because streaming
        responses are never cached.
        """
        clean_params = {k: v for k, v in params.items() if k != "stream"}
        raw = json.dumps(
            [model, messages, clean_params],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    # ── Public API ───────────────────────────────────────────────────────

    async def get(
        self,
        model: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return a cached response or ``None`` on miss."""
        key = self._make_key(model, messages, params)
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if time.monotonic() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            entry.accessed_at = time.monotonic()
            self._hits += 1
            return entry.response

    async def set(
        self,
        model: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
        response: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Store a response in the cache."""
        key = self._make_key(model, messages, params)
        effective_ttl = ttl if ttl is not None else get_cache_ttl()
        async with self._lock:
            self._evict_if_needed()
            self._cache[key] = CacheEntry(response, effective_ttl)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._cache.clear()

    def stats(self) -> dict[str, Any]:
        """Return current cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_entries": get_cache_max_entries(),
            "enabled": is_cache_enabled(),
            "ttl": get_cache_ttl(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }

    # ── Internals ────────────────────────────────────────────────────────

    def _evict_if_needed(self) -> None:
        """Remove expired entries, then LRU-evict if still over limit."""
        now = time.monotonic()
        expired_keys = [k for k, v in self._cache.items() if now > v.expires_at]
        for k in expired_keys:
            del self._cache[k]

        max_entries = get_cache_max_entries()
        while len(self._cache) >= max_entries:
            if not self._cache or max_entries <= 0:
                break
            oldest_key = min(self._cache, key=lambda k: self._cache[k].accessed_at)
            del self._cache[oldest_key]


__all__ = [
    "PromptCache",
    "CacheEntry",
    "is_cache_enabled",
    "set_cache_enabled",
    "get_cache_ttl",
    "set_cache_ttl",
    "get_cache_max_entries",
    "set_cache_max_entries",
]
