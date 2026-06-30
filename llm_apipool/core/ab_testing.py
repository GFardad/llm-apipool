"""A/B testing manager for llm-apipool.

Allows splitting traffic between two models for the same capability
so users can compare latency, error rate, and token consumption
side-by-side in the dashboard.

Assignment is hash-based: ``hash(uid + experiment_id) % 100 < weight_a``
ensures the same UID always gets the same variant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ABExperiment:
    """Configuration for a single A/B test experiment.

    Attributes
    ----------
    experiment_id:
        Unique identifier for this experiment.
    model_a:
        The control model (e.g. ``"llama-3.3-70b-versatile"``).
    model_b:
        The challenger model (e.g. ``"qwen-3-32b"``).
    weight_a:
        Fraction of traffic to route to model A (0.0 – 1.0).
        Model B gets ``1 - weight_a``.
    capability:
        The capability this experiment applies to
        (e.g. ``"general_purpose"``, ``"fast"``).
    enabled:
        When ``False`` the experiment is skipped during routing.
    created_at:
        ISO-8601 timestamp of creation.
    """

    experiment_id: str
    model_a: str
    model_b: str
    weight_a: float = 0.5
    capability: str = "general_purpose"
    enabled: bool = True
    created_at: str = ""


class ABTestManager:
    """Manages A/B test experiments in-memory.

    Experiments are stored in a dict keyed by ``experiment_id``.
    This is intentionally ephemeral — state is lost on restart,
    which is acceptable for the MVP.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, ABExperiment] = {}

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add_experiment(self, experiment: ABExperiment) -> None:
        """Register a new experiment (replaces any existing with the same id)."""
        if not experiment.created_at:
            experiment.created_at = datetime.now(timezone.utc).isoformat()
        self._experiments[experiment.experiment_id] = experiment

    def remove_experiment(self, experiment_id: str) -> None:
        """Remove an experiment by id.  No-op if it does not exist."""
        self._experiments.pop(experiment_id, None)

    def get_experiment(self, experiment_id: str) -> ABExperiment | None:
        """Return the experiment, or ``None`` if it does not exist."""
        return self._experiments.get(experiment_id)

    def get_all_experiments(self) -> dict[str, dict[str, Any]]:
        """Return a JSON-safe ``{experiment_id: {...}}`` dict of all experiments."""
        return {
            eid: {
                "experiment_id": e.experiment_id,
                "model_a": e.model_a,
                "model_b": e.model_b,
                "weight_a": e.weight_a,
                "capability": e.capability,
                "enabled": e.enabled,
                "created_at": e.created_at,
            }
            for eid, e in self._experiments.items()
        }

    # ── Assignment ──────────────────────────────────────────────────────────

    def get_assignment(self, experiment_id: str, uid: str) -> str | None:
        """Determine which model a UID should use for *experiment_id*.

        Returns ``"model_a"``, ``"model_b"``, or ``None`` when the
        experiment does not exist or is disabled.
        """
        exp = self._experiments.get(experiment_id)
        if exp is None or not exp.enabled:
            return None

        h = hashlib.md5(f"{uid}:{experiment_id}".encode()).hexdigest()
        bucket = int(h, 16) % 100

        if bucket < exp.weight_a * 100:
            return exp.model_a
        return exp.model_b

    # ── Results (read from audit_log) ───────────────────────────────────────

    def get_results(self, experiment_id: str, store: Any) -> dict[str, Any]:
        """Compare metrics between model A and B for this experiment.

        Queries the audit log for entries matching each model and
        returns side-by-side comparison data.

        Parameters
        ----------
        experiment_id:
            The experiment to analyse.
        store:
            A ``KeyStore`` instance with ``get_audit_log()``.

        Returns
        -------
        A dict with keys ``"model_a"``, ``"model_b"``, and
        ``"experiment"`` containing the experiment metadata.
        """
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return {"error": f"Experiment '{experiment_id}' not found"}

        days = 7
        entries = store.get_audit_log(days=days, limit=5000)
        models = {exp.model_a: "a", exp.model_b: "b"}

        grouped: dict[str, list[dict[str, Any]]] = {"a": [], "b": []}
        for entry in entries:
            model = entry.get("model", "")
            group = models.get(model)
            if group is not None:
                grouped[group].append(entry)

        def _summarise(entries: list[dict[str, Any]], label: str) -> dict[str, Any]:
            total = len(entries)
            if total == 0:
                return {
                    "model": label,
                    "requests": 0,
                    "avg_latency_ms": 0,
                    "error_rate": 0.0,
                    "avg_tokens": 0,
                    "total_tokens": 0,
                }
            latencies = [e.get("latency_ms", 0) for e in entries if e.get("latency_ms")]
            errors = sum(1 for e in entries if not e.get("success", True))
            tokens = sum(e.get("tokens_out", 0) for e in entries)
            avg_lat = sum(latencies) / len(latencies) if latencies else 0
            return {
                "model": label,
                "requests": total,
                "avg_latency_ms": round(avg_lat, 1),
                "error_rate": round(errors / total, 4),
                "avg_tokens": round(tokens / total, 1) if total else 0,
                "total_tokens": tokens,
            }

        a_stats = _summarise(grouped["a"], exp.model_a)
        b_stats = _summarise(grouped["b"], exp.model_b)

        def _delta(a_val: float, b_val: float) -> float:
            return round(b_val - a_val, 1)

        comparison = {
            "requests": {
                "a": a_stats["requests"],
                "b": b_stats["requests"],
                "delta": _delta(float(a_stats["requests"]), float(b_stats["requests"])),
            },
            "avg_latency_ms": {
                "a": a_stats["avg_latency_ms"],
                "b": b_stats["avg_latency_ms"],
                "delta": _delta(a_stats["avg_latency_ms"], b_stats["avg_latency_ms"]),
            },
            "error_rate": {
                "a": a_stats["error_rate"],
                "b": b_stats["error_rate"],
                "delta": _delta(a_stats["error_rate"], b_stats["error_rate"]),
            },
            "avg_tokens": {
                "a": a_stats["avg_tokens"],
                "b": b_stats["avg_tokens"],
                "delta": _delta(a_stats["avg_tokens"], b_stats["avg_tokens"]),
            },
        }

        return {
            "experiment": {
                "experiment_id": exp.experiment_id,
                "model_a": exp.model_a,
                "model_b": exp.model_b,
                "weight_a": exp.weight_a,
                "capability": exp.capability,
                "enabled": exp.enabled,
            },
            "model_a": a_stats,
            "model_b": b_stats,
            "comparison": comparison,
        }


__all__ = [
    "ABExperiment",
    "ABTestManager",
    "get_ab_testing_enabled",
    "set_ab_testing_enabled",
    "get_ab_testing_traffic_percent",
    "set_ab_testing_traffic_percent",
    "get_ab_testing_method",
    "set_ab_testing_method",
]


# Global A/B testing settings (simplified getter/setter for MVP)
_AB_TESTING_ENABLED = False
_AB_TESTING_TRAFFIC_PERCENT = 50
_AB_TESTING_METHOD: str = "hash"


def get_ab_testing_enabled() -> bool:
    """Return whether A/B testing is enabled globally."""
    return _AB_TESTING_ENABLED


def set_ab_testing_enabled(enabled: bool) -> None:
    """Enable or disable A/B testing globally."""
    global _AB_TESTING_ENABLED  # noqa: PLW0603
    _AB_TESTING_ENABLED = enabled


def get_ab_testing_traffic_percent() -> int:
    """Return the traffic split percentage for model A (default 50)."""
    return _AB_TESTING_TRAFFIC_PERCENT


def set_ab_testing_traffic_percent(percent: int) -> None:
    """Set the traffic split percentage for model A (0-100)."""
    global _AB_TESTING_TRAFFIC_PERCENT  # noqa: PLW0603
    _AB_TESTING_TRAFFIC_PERCENT = percent


def get_ab_testing_method() -> str:
    """Return the A/B testing method (default 'hash')."""
    return _AB_TESTING_METHOD


def set_ab_testing_method(method: str) -> None:
    """Set the A/B testing method ('hash' or 'round-robin')."""
    global _AB_TESTING_METHOD  # noqa: PLW0603
    _AB_TESTING_METHOD = method
