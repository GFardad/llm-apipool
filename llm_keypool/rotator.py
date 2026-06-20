"""Key rotation and rate-limit-aware key selection with model quality tiering."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typing import Any

from .key_store import KeyStore
from .providers.headers import extract_cooldown

MONTHS_IN_YEAR = 12
MIN_QUALITY_TIER = 1
MAX_QUALITY_TIER = 4


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

        self._order: dict[str, list[int]] = {}
        self._cursor: dict[str, int] = {}
        self._slot_count: dict[int, int] = {}
        self._loaded_cap_keys: set[str] = set()
        # track which cap_key context each key_id was last selected under
        self._key_last_cap_key: dict[int, str] = {}

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

    def _ensure_order(self, ck: str, capabilities: list[str], active_ids: set[int]) -> None:
        """Build or refresh the ordered key list for a capability context.

        Keys are filtered to the configured quality tier range
        [quality_tier, max_fallback_tier] and sorted by tier ascending
        (best models first), then by score descending (least-used first within tier).
        """
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
            tier = get_model_tier(model)
            if not (self._quality_tier <= tier <= self._max_fallback_tier):
                continue
            score = _score_key(k, cfg)
            candidates.append((tier, score, k))

        # Sort by tier ascending (best first), then score descending (least used first)
        candidates.sort(key=lambda x: (x[0], -x[1]))
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
    ) -> dict[str, Any] | None:
        """Select the best available key for the given capabilities."""
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        ck = _cap_key(capabilities)
        active = self.store.get_active_keys(capabilities)
        if not active:
            return None

        active_map = {k["id"]: k for k in active}
        self._ensure_order(ck, capabilities, set(active_map.keys()))

        order  = self._order[ck]
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
        cfg   = self.configs.get(best["provider"], {})
        extra = json.loads(best["extra_params"] or "{}")

        # Use user-specified base_url_override if present, otherwise use provider config default
        raw_base_url = best.get("base_url_override") or cfg.get("base_url", "")
        base_url = raw_base_url
        if "{account_id}" in base_url:
            base_url = base_url.format(account_id=extra.get("account_id", ""))

        slot_pos = self._slot_count.get(best["id"], 0) + 1
        self._key_last_cap_key[best["id"]] = ck

        return {
            "key_id":            best["id"],
            "provider":          best["provider"],
            "api_key":           best["api_key"],
            "base_url":          base_url,
            "model":             best["model"] or _resolve_model(cfg, ck),
            "capabilities":      self.store.parse_capabilities(best),
            "cap_key":           ck,
            "subscriber_id":     subscriber_id,
            "openai_compatible": cfg.get("openai_compatible", True),
            "extra_params":      extra,
            "requests_today":    best["requests_today"],
            "tokens_used_today": best["tokens_used_today"],
            "cycle_position":    slot_pos,
            "rotate_every":      self.rotate_every,
        }

    def peek_current_key(self, capabilities: list[str] | str) -> dict[str, Any] | None:
        """Return the key that would be selected next without mutating state."""
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        ck = _cap_key(capabilities)
        active = self.store.get_active_keys(capabilities)
        if not active:
            return None

        active_map = {k["id"]: k for k in active}
        self._ensure_order(ck, capabilities, set(active_map.keys()))

        order      = self._order[ck]
        cursor     = self._cursor.get(ck, 0) % len(order)
        slot_count = dict(self._slot_count)

        for _ in range(len(order) + 1):
            key_id = order[cursor % len(order)]
            if key_id in active_map and slot_count.get(key_id, 0) < self.rotate_every:
                break
            cursor = (cursor + 1) % len(order)
        else:
            return None

        best = active_map[order[cursor]]
        cfg  = self.configs.get(best["provider"], {})
        slot_pos = slot_count.get(best["id"], 0) + 1
        return {
            "key_id":            best["id"],
            "provider":          best["provider"],
            "model":             best["model"] or _resolve_model(cfg, ck),
            "capabilities":      self.store.parse_capabilities(best),
            "requests_today":    best["requests_today"],
            "tokens_used_today": best["tokens_used_today"],
            "cooldown_until":    best.get("cooldown_until"),
            "cycle_position":    slot_pos,
            "rotate_every":      self.rotate_every,
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
