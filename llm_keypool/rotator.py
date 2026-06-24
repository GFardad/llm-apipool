"""Key rotation and rate-limit-aware key selection with model quality tiering."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typing import Any

from .key_store import KeyStore
from .providers.headers import extract_cooldown


def _tier_fallback_allowed() -> bool:
    """Check whether tier fallback is currently enabled (runtime toggle)."""
    try:
        from .core.tier_fallback import is_tier_fallback_enabled
        return is_tier_fallback_enabled()
    except Exception:
        return True  # safe default

MONTHS_IN_YEAR = 12
MIN_QUALITY_TIER = 1
MAX_QUALITY_TIER = 4


def _get_model_features(model_name: str) -> dict[str, Any] | None:
    """Get model features from metadata cache."""
    try:
        from ..core.model_metadata import get_model_features
        return get_model_features(model_name)
    except Exception:
        return None


def _next_utc_midnight() -> str:
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    ).isoformat()


def _next_first_of_month() -> str:
    now = datetime.now(UTC)
    month = now.month + 1
    year = now.year + (1 if month > MONTHS_IN_YEAR else 0)
    month = 1 if month > MONTHS_IN_YEAR else month
    return now.replace(
        year=year, month=month, day=1,
        hour=0, minute=0, second=0, microsecond=0,
    ).isoformat()


def _rolling(seconds: int) -> Callable[[], str]:
    def _inner() -> str:
        return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
    return _inner


_FALLBACK_STRATEGIES = {
    "daily_utc_midnight":      _next_utc_midnight,
    "first_of_calendar_month": _next_first_of_month,
    "rolling_60":              _rolling(60),
    "rolling_65":              _rolling(65),
    "rolling_120":             _rolling(120),
}
_DEFAULT_FALLBACK = _rolling(60)

# ---------------------------------------------------------------------------
# Group-based routing utilities
# ---------------------------------------------------------------------------

_GROUP_PATTERN = re.compile(r"^g(\d+)$")


def extract_group(model_name: str) -> str:
    """Extract group from model name.

    If model matches gN pattern (e.g., 'g1', 'g2'), returns 'gN'.
    Otherwise returns 'default'.
    """
    if _GROUP_PATTERN.match(model_name):
        return model_name
    return "default"


def parse_context_filter(model_param: str) -> tuple[str, int] | None:
    """Parse model parameter for context window filtering.

    Syntax: {prefix}.{number}{k|M} (e.g., 'g1.128k', 'opus.1M', 'default.64k').
    Returns (group, min_context_tokens) or None if no filter syntax.

    If prefix matches gN, filter applies to that specific group.
    Otherwise filter applies to 'default' group.
    'k' multiplies by 1,000; 'M' multiplies by 1,000,000.
    """
    match = re.match(r"^([a-zA-Z0-9_-]+)\.(\d+)(k|M)$", model_param, re.IGNORECASE)
    if not match:
        return None
    prefix, number, suffix = match.groups()
    min_context = int(number) * (1000 if suffix.lower() == "k" else 1000000)
    group = prefix if _GROUP_PATTERN.match(prefix) else "default"
    return group, min_context

# ---------------------------------------------------------------------------
# Model quality tiers
# ---------------------------------------------------------------------------

_MODEL_TIER_MAP: dict[str, int] | None = None
_MODEL_TIER_PATH = Path(__file__).parent / "config" / "model_quality.json"


def _load_model_tiers() -> dict[str, int]:
    """Load model → tier mapping from model_quality.json.

    Returns a dict of {model_name: tier_number (1-4)}.
    Returns an empty dict if the file is missing or unparseable.
    """
    global _MODEL_TIER_MAP  # noqa: PLW0603
    if _MODEL_TIER_MAP is not None:
        return _MODEL_TIER_MAP
    if not _MODEL_TIER_PATH.exists():
        _MODEL_TIER_MAP = {}
        return _MODEL_TIER_MAP
    try:
        with _MODEL_TIER_PATH.open() as f:
            data = json.load(f)
        result: dict[str, int] = {}
        for tier_key in ("tier1", "tier2", "tier3", "tier4"):
            tier_num = int(tier_key[-1])  # "tier1" → 1
            for model in data.get(tier_key, []):
                result[model] = tier_num
        _MODEL_TIER_MAP = result
    except (OSError, json.JSONDecodeError):
        _MODEL_TIER_MAP = {}
    return _MODEL_TIER_MAP


def get_model_tier(model: str) -> int:
    """Return the quality tier (1 = best, 4 = worst) for a model name.

    Falls back to tier 4 for unknown / unrecognised models.
    """
    tier_map = _load_model_tiers()
    return tier_map.get(model, 4)


def _fallback_from_config(cfg: dict[str, Any]) -> Callable[[], str]:
    key = cfg.get("cooldown_fallback", {}).get("strategy", "rolling_60")
    return _FALLBACK_STRATEGIES.get(key, _DEFAULT_FALLBACK)


def _score_key(key: dict[str, Any], cfg: dict[str, Any]) -> float:
    rpd = cfg.get("limits", {}).get("rpd")
    return float(rpd - key["requests_today"]) if rpd else float(-key["requests_today"])


def _key_priority(key: dict[str, Any]) -> int:
    """Get priority for a key, defaulting to 0 if not set."""
    return key.get("priority") or 0


def _resolve_model(cfg: dict[str, Any], cap_key: str) -> str:
    models = cfg.get("models", {})
    if isinstance(models, list):
        return models[0] if models else ""
    if isinstance(models, dict):
        cat_models = models.get(cap_key, [])
        return cat_models[0] if cat_models else ""
    return str(cfg.get("default_model", ""))


def _cap_key(capabilities: list[str]) -> str:
    """Canonical string key for a capabilities set, used as rotation state key."""
    return ",".join(sorted(capabilities))


class Rotator:
    """Selects best key by model quality tier, handles 429 cooldowns, and rotates evenly."""

    def __init__(
        self,
        store: KeyStore,
        provider_configs: dict[str, Any],
        rotate_every: int = 5,
        quality_tier: int = 1,
        max_fallback_tier: int = 4,
    ) -> None:
        """Initialize the Rotator.

        Parameters
        ----------
        store:
            KeyStore instance.
        provider_configs:
            Provider configuration dict (from providers.json).
        rotate_every:
            Requests per key before forcing a rotation.
        quality_tier:
            Preferred model quality tier (1 = best). The rotator will try
            this tier first and fall back through worse tiers when keys are exhausted.
        max_fallback_tier:
            Worst tier the rotator is allowed to fall back to (inclusive).
            Must be >= quality_tier.

        """
        if quality_tier < MIN_QUALITY_TIER or quality_tier > MAX_QUALITY_TIER:
            msg = f"quality_tier must be {MIN_QUALITY_TIER}-{MAX_QUALITY_TIER}, got {quality_tier}"
            raise ValueError(msg)
        if max_fallback_tier < MIN_QUALITY_TIER or max_fallback_tier > MAX_QUALITY_TIER:
            msg = f"max_fallback_tier must be {MIN_QUALITY_TIER}-{MAX_QUALITY_TIER}, got {max_fallback_tier}"
            raise ValueError(msg)
        if quality_tier > max_fallback_tier:
            msg = (
                f"quality_tier ({quality_tier}) must be <= "
                f"max_fallback_tier ({max_fallback_tier})"
            )
            raise ValueError(msg)

        self.store = store
        self.configs = provider_configs
        self.rotate_every = rotate_every
        self._quality_tier = quality_tier
        self._max_fallback_tier = max_fallback_tier

        # ── Force-provider override ────────────────────────────────────────
        # When set, get_best_key() returns a synthetic key_data pointing at
        # this provider regardless of what's in the key database.
        self._force_provider: str | None = None
        self._force_model: str | None = None

        self._order: dict[str, list[int]] = {}
        self._cursor: dict[str, int] = {}
        self._slot_count: dict[int, int] = {}
        self._loaded_cap_keys: set[str] = set()
        # track which cap_key context each key_id was last selected under
        self._key_last_cap_key: dict[int, str] = {}

    # ── Force-provider routing override ──────────────────────────────────

    @property
    def force_provider(self) -> str | None:
        """If set, all routing goes to this provider regardless of DB keys."""
        return self._force_provider

    def set_force_provider(self, provider: str, model: str | None = None) -> None:
        """Force all chat-completion routing to *provider* with optional *model*.

        When enabled, ``get_best_key()`` returns a synthetic key_data with no
        real API key — the provider must support ``no_auth`` (like opencode_zen).
        Call ``clear_force_provider()`` to restore normal DB-backed routing.
        """
        self._force_provider = provider
        self._force_model = model

    def clear_force_provider(self) -> None:
        """Restore normal DB-backed routing."""
        self._force_provider = None
        self._force_model = None

    def _load_state(self, ck: str) -> None:
        if ck in self._loaded_cap_keys:
            return
        cursor, slot_counts = self.store.load_rotation_state(ck)
        self._cursor[ck] = cursor
        self._slot_count.update(slot_counts)
        self._loaded_cap_keys.add(ck)

    def _persist_state(self, ck: str) -> None:
        self.store.save_rotation_state(
            ck,
            self._cursor.get(ck, 0),
            self._slot_count,
        )

    def _ensure_order(
        self,
        ck: str,
        capabilities: list[str],
        active_ids: set[int],
        min_context: int | None = None,
        require_tools: bool | None = None,
        require_vision: bool | None = None,
    ) -> None:
        """Build or refresh the ordered key list for a capability context."""
        self._load_state(ck)
        current = self._order.get(ck, [])
        if set(current) == active_ids:
            return

        all_keys = self.store.get_all_keys()
        candidates: list[tuple[int, float, dict[str, Any]]] = []

        for k in all_keys:
            if not k["is_active"]:
                continue
            if not any(c in self.store.parse_capabilities(k) for c in capabilities):
                continue
            cfg = self.configs.get(k["provider"], {})
            model = k["model"] or _resolve_model(cfg, ck)
            
            # Filter by model features if specified
            features = _get_model_features(model)
            if min_context is not None and features:
                if features.get("context", 0) < min_context:
                    continue
            if require_tools is True and features and not features.get("tools", False):
                continue
            if require_vision is True and features and not features.get("vision", False):
                continue
            
            tier = get_model_tier(model)
            effective_max = self._max_fallback_tier if _tier_fallback_allowed() else self._quality_tier
            if not (self._quality_tier <= tier <= effective_max):
                continue
            score = _score_key(k, cfg)
            candidates.append((tier, score, k))

        candidates.sort(key=lambda x: (-_key_priority(x[2]), x[0], -x[1]))
        ordered = [k for _, _, k in candidates]

        self._order[ck] = [k["id"] for k in ordered]
        if ck not in self._cursor:
            self._cursor[ck] = 0
        else:
            self._cursor[ck] %= max(len(self._order[ck]), 1)
        for k in ordered:
            self._slot_count.setdefault(k["id"], 0)

    def get_best_key(
        self,
        capabilities: list[str] | str,
        subscriber_id: str = "unknown",
        min_context: int | None = None,
        require_tools: bool | None = None,
        require_vision: bool | None = None,
    ) -> dict[str, Any] | None:
        """Select the best available key for the given capabilities."""
        # ── Force-provider override — bypass key DB entirely ────────────
        if self._force_provider:
            cfg = self.configs.get(self._force_provider, {})
            forced_model = self._force_model or cfg.get("default_model", "deepseek-v4-flash-free")
            caps = capabilities if isinstance(capabilities, list) else [capabilities]
            return {
                "key_id": -1,  # sentinel — DB-independent
                "provider": self._force_provider,
                "api_key": "",
                "base_url": cfg.get("base_url", ""),
                "model": forced_model,
                "capabilities": caps,
                "cap_key": "forced",
                "subscriber_id": subscriber_id,
                "openai_compatible": cfg.get("openai_compatible", True),
                "no_auth": cfg.get("no_auth", False),
                "extra_params": {},
                "requests_today": 0,
                "tokens_used_today": 0,
                "cycle_position": 1,
                "rotate_every": 1,
            }

        if isinstance(capabilities, str):
            capabilities = [capabilities]
        ck = _cap_key(capabilities)
        active = self.store.get_active_keys(capabilities)
        if not active:
            return None

        active_map = {k["id"]: k for k in active}
        self._ensure_order(ck, capabilities, set(active_map.keys()), min_context, require_tools, require_vision)

        order = self._order[ck]
        cursor = self._cursor.get(ck, 0) % len(order)

        reset_done = False
        for _ in range(len(order) + 1):
            key_id = order[cursor % len(order)]
            if key_id in active_map and self._slot_count.get(key_id, 0) < self.rotate_every:
                break
            cursor = (cursor + 1) % len(order)
            if not reset_done and cursor == self._cursor.get(ck, 0) % len(order):
                for kid in order:
                    self._slot_count[kid] = 0
                reset_done = True
        else:
            return None

        self._cursor[ck] = cursor
        best = active_map[order[cursor]]
        cfg = self.configs.get(best["provider"], {})
        extra = json.loads(best["extra_params"] or "{}")

        raw_base_url = best.get("base_url_override") or cfg.get("base_url", "")
        base_url = raw_base_url
        if "{account_id}" in base_url:
            base_url = base_url.format(account_id=extra.get("account_id", ""))

        slot_pos = self._slot_count.get(best["id"], 0) + 1
        self._key_last_cap_key[best["id"]] = ck

        return {
            "key_id": best["id"],
            "provider": best["provider"],
            "api_key": best["api_key"],
            "base_url": base_url,
            "model": best["model"] or _resolve_model(cfg, ck),
            "capabilities": self.store.parse_capabilities(best),
            "cap_key": ck,
            "subscriber_id": subscriber_id,
            "openai_compatible": cfg.get("openai_compatible", True),
            "no_auth": cfg.get("no_auth", False),
            "extra_params": extra,
            "requests_today": best["requests_today"],
            "tokens_used_today": best["tokens_used_today"],
            "cycle_position": slot_pos,
            "rotate_every": self.rotate_every,
        }

    def peek_current_key(
        self, capabilities: list[str] | str, min_context: int | None = None,
        require_tools: bool | None = None, require_vision: bool | None = None,
    ) -> dict[str, Any] | None:
        """Return the key that would be selected next without mutating state."""
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        ck = _cap_key(capabilities)
        active = self.store.get_active_keys(capabilities)
        if not active:
            return None

        active_map = {k["id"]: k for k in active}
        self._ensure_order(ck, capabilities, set(active_map.keys()), min_context, require_tools, require_vision)

        order = self._order[ck]
        cursor = self._cursor.get(ck, 0) % len(order)
        slot_count = dict(self._slot_count)

        for _ in range(len(order) + 1):
            key_id = order[cursor % len(order)]
            if key_id in active_map and slot_count.get(key_id, 0) < self.rotate_every:
                break
            cursor = (cursor + 1) % len(order)
        else:
            return None

        best = active_map[order[cursor]]
        cfg = self.configs.get(best["provider"], {})
        slot_pos = slot_count.get(best["id"], 0) + 1
        return {
            "key_id": best["id"],
            "provider": best["provider"],
            "model": best["model"] or _resolve_model(cfg, ck),
            "capabilities": self.store.parse_capabilities(best),
            "requests_today": best["requests_today"],
            "tokens_used_today": best["tokens_used_today"],
            "cooldown_until": best.get("cooldown_until"),
            "cycle_position": slot_pos,
            "rotate_every": self.rotate_every,
        }

    def handle_429(
        self,
        key_id: int,
        provider: str,
        headers: dict[str, Any] | None = None,
        subscriber_id: str = "unknown",
        model: str = "",
    ) -> str:
        """Handle a 429 rate-limit response and set cooldown."""
        if key_id == -1:  # synthetic forced key — no DB state to manage
            return ""
        headers = headers or {}
        cooldown = extract_cooldown(provider, headers, was_429=True)
        if cooldown is None:
            cfg = self.configs.get(provider, {})
            cooldown = _fallback_from_config(cfg)()
        self.store.record_usage(key_id, tokens=0, was_429=True, cooldown_until=cooldown)
        self._slot_count[key_id] = self._slot_count.get(key_id, 0) + 1
        ck = self._key_last_cap_key.get(key_id, "")
        if ck:
            self._persist_state(ck)
        self.store.log_audit(
            subscriber_id=subscriber_id,
            key_id=key_id,
            provider=provider,
            model=model,
            success=False,
            error="429 rate limit",
        )
        return cooldown

    def handle_success(  # noqa: PLR0913
        self,
        key_id: int,
        tokens_used: int,
        headers: dict[str, Any] | None = None,
        provider: str = "",
        tokens_in: int = 0,
        latency_ms: int = 0,
        subscriber_id: str = "unknown",
        model: str = "",
    ) -> None:
        """Handle a successful API response, record usage and audit log."""
        if key_id == -1:  # synthetic forced key — no DB state to manage
            return
        headers = headers or {}
        cooldown = extract_cooldown(provider, headers, was_429=False) if provider else None
        self.store.record_usage(key_id, tokens=tokens_used, was_429=False, cooldown_until=cooldown)
        self._slot_count[key_id] = self._slot_count.get(key_id, 0) + 1
        ck = self._key_last_cap_key.get(key_id, "")
        if ck:
            self._persist_state(ck)
        self.store.log_audit(
            subscriber_id=subscriber_id,
            key_id=key_id,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_used,
            latency_ms=latency_ms,
            success=True,
        )

    def get_earliest_retry(self, capabilities: list[str] | str) -> str | None:
        """Return the earliest cooldown expiry among matching keys, or None."""
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        all_keys = self.store.get_all_keys()
        cooldowns = [
            k["cooldown_until"] for k in all_keys
            if k["is_active"] and k["cooldown_until"]
            and any(c in self.store.parse_capabilities(k) for c in capabilities)
        ]
        return min(cooldowns) if cooldowns else None
