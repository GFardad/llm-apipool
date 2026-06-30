"""Dedicated query operations for analytics and aggregations.

Provides high-level query functions that operate on the existing
``KeyStore`` SQLite database for analytics, sticky sessions, and
fallback configuration management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from llm_apipool.key_store import KeyStore


def get_active_key_count(store: KeyStore) -> int:
    """Return the number of active (non-cooldown, is_active) keys."""
    keys = store.get_all_keys()
    return sum(1 for k in keys if k["is_active"] and not k.get("cooldown_until"))


def get_provider_breakdown(store: KeyStore) -> dict[str, int]:
    """Return a dict mapping provider name to active key count."""
    keys = store.get_all_keys()
    counts: dict[str, int] = {}
    for k in keys:
        if k["is_active"]:
            counts[k["provider"]] = counts.get(k["provider"], 0) + 1
    return counts


def get_recent_usage(
    store: KeyStore,
    hours: int = 24,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return the most recent audit log entries."""
    raw = store.get_audit_log(days=1, limit=limit)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    recent = []
    for entry in raw:
        ts = entry.get("ts", "")
        if ts and len(ts) >= 19:
            try:
                entry_dt = datetime.fromisoformat(ts)
                if entry_dt >= cutoff:
                    recent.append(entry)
            except (ValueError, TypeError):
                recent.append(entry)
    return recent[:limit]


def get_key_health_summary(store: KeyStore) -> dict[str, Any]:
    """Return a summary of key pool health."""
    keys = store.get_all_keys()
    total = len(keys)
    active = sum(1 for k in keys if k["is_active"])
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cooled = sum(
        1
        for k in keys
        if k.get("cooldown_until")
        and k["cooldown_until"] > now_str
    )
    return {
        "total": total,
        "active": active,
        "cooldown": cooled,
        "inactive": total - active,
    }


def get_strategy_settings(store: KeyStore) -> dict[str, Any]:
    """Return current routing strategy and related settings."""
    from llm_apipool.core.router import get_all_penalties, get_routing_strategy

    penalties = get_all_penalties()
    return {
        "strategy": get_routing_strategy(),
        "penalty_count": len(penalties),
    }


__all__ = [
    "get_active_key_count",
    "get_provider_breakdown",
    "get_recent_usage",
    "get_key_health_summary",
    "get_strategy_settings",
]
