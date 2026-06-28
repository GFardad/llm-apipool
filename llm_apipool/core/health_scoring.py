"""Key health scoring — composite 0-100 score from audit log and cooldown data.

Used by the dashboard for display and by the rotator for weighted scoring.
Leverages existing DB columns (accuracy_score, speed_score, reliability_score)
and audit_log data — no new schema changes required.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Weights for the three axes of the health score (must sum to 1.0)
HEALTH_WEIGHTS = {
    "success_rate": 0.50,
    "avg_latency": 0.25,
    "cooldown_freq": 0.25,
}

# Clamp thresholds
MAX_LATENCY_MS = 5000  # >= this → 0 points for latency axis
MAX_COOLDOWNS_PER_HOUR = 10  # >= this → 0 points for cooldown axis


def _compute_success_rate(audit_data: list[dict[str, Any]]) -> float:
    """Score [0..100] from last 100 audit entries (or all if < 100)."""
    recent = audit_data[:100] if len(audit_data) > 100 else audit_data
    if not recent:
        return 50.0  # neutral default — no data yet
    successes = sum(1 for e in recent if e.get("success"))
    return (successes / len(recent)) * 100.0


def _compute_avg_latency(audit_data: list[dict[str, Any]]) -> float:
    """Score [0..100] from average latency of last 50 requests.

    0ms → 100 points, >= MAX_LATENCY_MS → 0 points, linear in between.
    """
    recent = [e for e in audit_data[:50] if e.get("latency_ms", 0) > 0]
    if not recent:
        return 50.0  # neutral — no data
    avg = sum(e["latency_ms"] for e in recent) / len(recent)
    clamped = min(avg, MAX_LATENCY_MS)
    # Linear interpolation: 0ms=100, MAX_LATENCY_MS=0
    return ((MAX_LATENCY_MS - clamped) / MAX_LATENCY_MS) * 100.0


def _compute_cooldown_freq(metrics_data: dict[str, Any]) -> float:
    """Score [0..100] from cooldown frequency in the last hour.

    Uses model_cooldowns table data (cooldown_count) when available,
    falling back to in-memory cooldown frequency.
    """
    count = metrics_data.get("cooldown_count", 0)
    if count <= 0:
        return 100.0
    clamped = min(count, MAX_COOLDOWNS_PER_HOUR)
    return ((MAX_COOLDOWNS_PER_HOUR - clamped) / MAX_COOLDOWNS_PER_HOUR) * 100.0


def compute_health_score(
    key_id: int,  # noqa: ARG001 — used by callers for context, not needed internally
    audit_data: list[dict[str, Any]],
    metrics_data: dict[str, Any],
) -> int:
    """Compute composite health score 0-100 for an API key.

    Parameters
    ----------
    key_id:
        Key ID (provided for caller context; not used in computation).
    audit_data:
        Recent audit log entries for this key (list of dicts with
        ``success``, ``latency_ms``, etc.).
    metrics_data:
        Key metrics including ``cooldown_count`` (from
        model_cooldowns table).

    Returns
    -------
    int
        Health score 0-100 (higher = healthier).

    Weights
    -------
    success_rate: 50%
        From audit_log: success / total, last 100 requests.
    avg_latency: 25%
        From audit_log: average latency_ms, last 50 requests.
    cooldown_freq: 25%
        From model_cooldowns.cooldown_count.
    """
    success_rate = _compute_success_rate(audit_data)
    avg_latency = _compute_avg_latency(audit_data)
    cooldown_freq = _compute_cooldown_freq(metrics_data)

    raw = (
        HEALTH_WEIGHTS["success_rate"] * success_rate
        + HEALTH_WEIGHTS["avg_latency"] * avg_latency
        + HEALTH_WEIGHTS["cooldown_freq"] * cooldown_freq
    )
    return max(0, min(100, round(raw)))


def compute_health_score_for_key(
    key_id: int,
    store: Any,
    audit_days: int = 7,
) -> int:
    """Convenience wrapper: fetches audit log + metrics from store and scores.

    Parameters
    ----------
    key_id:
        The DB key id.
    store:
        ``KeyStore`` instance (must have ``get_audit_log`` and
        ``get_model_cooldown_counts`` methods).
    audit_days:
        How many days of audit history to consider (default 7).

    Returns
    -------
    int
        Health score 0-100.
    """
    audit = store.get_audit_log(days=audit_days, limit=200)
    # Filter to entries for this specific key
    key_audit = [e for e in audit if e.get("key_id") == key_id]

    # Gather cooldown counts from model_cooldowns
    cooldown_count = 0
    key_data = store.get_key_by_id(key_id)
    if key_data and key_data.get("model"):
        model_db_id = store.get_model_db_id(key_data["provider"], key_data["model"])
        if model_db_id is not None:
            counts = store.get_model_cooldown_counts(model_db_id)
            cooldown_count = counts.get("total", 0)

    metrics_data: dict[str, Any] = {
        "cooldown_count": cooldown_count,
    }
    return compute_health_score(key_id, key_audit, metrics_data)


__all__ = [
    "HEALTH_WEIGHTS",
    "compute_health_score",
    "compute_health_score_for_key",
]
