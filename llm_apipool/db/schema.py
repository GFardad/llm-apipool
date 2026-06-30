"""Combined database schema — llm-apipool + FreeLLMAPI tables.

Existing ``key_store.py`` creates and manages tables via raw SQL.
This schema file documents the full combined schema using dataclass
representations and provides DDL statements for migration-free setups.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiKeyRow:
    """Row representation of the ``api_keys`` table."""

    id: int = 0
    provider: str = ""
    api_key: str = ""
    model: str | None = None
    base_url_override: str | None = None
    capabilities: str = ""
    is_active: int = 1
    priority: int = 100
    requests_today: int = 0
    requests_month: int = 0
    total_tokens: int = 0
    cooldown_until: str | None = None
    last_used: str | None = None
    last_429: str | None = None
    created_at: str = ""
    context_size: int | None = None
    accuracy_score: int = 50
    speed_score: int = 50
    reliability_score: int = 50
    group_name: str = "default"
    is_sticky_enabled: int = 0
    sticky_ttl_hours: int = 1
    extra_params: str = "{}"
    slot: int = 0


@dataclass
class AuditLogRow:
    """Row representation of the ``audit_log`` table."""

    id: int = 0
    timestamp: str = ""
    subscriber_id: str = ""
    key_id: int | None = None
    provider: str = ""
    model: str = ""
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    ttfb_ms: int | None = None
    status: str = "success"
    error: str | None = None
    cache_hit: int = 0
    streaming: int = 0


@dataclass
class ModelRow:
    """Model metadata, one row per model variant per platform."""

    id: int = 0
    platform: str = ""
    model_id: str = ""
    display_name: str = ""
    intelligence_rank: int = 999
    size_label: str = "Medium"
    monthly_token_budget: int | None = None
    rpm_limit: int | None = None
    rpd_limit: int | None = None
    tpm_limit: int | None = None
    tpd_limit: int | None = None
    supports_vision: int = 0
    supports_tools: int = 1
    context_window: int = 8192
    key_id: int | None = None


@dataclass
class FallbackConfigRow:
    """Per-model fallback chain and profile binding."""

    id: int = 0
    model_db_id: int = 0
    priority: int = 100
    enabled: int = 1
    profile_id: int | None = None


@dataclass
class ProfileRow:
    """Named fallback profile for grouped routing."""

    id: int = 0
    name: str = ""
    description: str = ""
    is_active: int = 1


@dataclass
class SettingRow:
    """Key-value settings store for the dashboard UI."""

    key: str = ""
    value: str = ""


@dataclass
class StickySessionRow:
    """Active sticky session binding a session_id to a specific key/model."""

    id: int = 0
    session_id: str = ""
    key_id: int = 0
    provider: str = ""
    model: str = ""
    expires_at: str = ""


@dataclass
class RequestLogRow:
    """Per-request log with latency, token counts, and errors."""

    id: int = 0
    created_at: str = ""
    platform: str = ""
    model_id: str = ""
    status: str = "success"
    latency_ms: int = 0
    ttfb_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    subscriber_id: str = ""
    error: str | None = None


# DDL statements for migration-free environments
DDL_STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        model_id TEXT NOT NULL,
        display_name TEXT,
        intelligence_rank INTEGER DEFAULT 999,
        size_label TEXT DEFAULT 'Medium',
        monthly_token_budget INTEGER,
        rpm_limit INTEGER,
        rpd_limit INTEGER,
        tpm_limit INTEGER,
        tpd_limit INTEGER,
        supports_vision INTEGER DEFAULT 0,
        supports_tools INTEGER DEFAULT 1,
        context_window INTEGER DEFAULT 8192,
        key_id INTEGER,
        UNIQUE(platform, model_id)
    )""",
    """CREATE TABLE IF NOT EXISTS fallback_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_db_id INTEGER NOT NULL,
        priority INTEGER DEFAULT 100,
        enabled INTEGER DEFAULT 1,
        profile_id INTEGER,
        FOREIGN KEY (model_db_id) REFERENCES models(id),
        FOREIGN KEY (profile_id) REFERENCES profiles(id)
    )""",
    """CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sticky_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL UNIQUE,
        key_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS request_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        platform TEXT NOT NULL,
        model_id TEXT NOT NULL,
        status TEXT DEFAULT 'success',
        latency_ms INTEGER DEFAULT 0,
        ttfb_ms INTEGER,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        subscriber_id TEXT DEFAULT '',
        error TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sticky_sessions_session_id ON sticky_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_request_log_created_at ON request_log(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_models_platform_model_id ON models(platform, model_id)",
]


__all__ = [
    "ApiKeyRow",
    "AuditLogRow",
    "ModelRow",
    "FallbackConfigRow",
    "ProfileRow",
    "SettingRow",
    "StickySessionRow",
    "RequestLogRow",
    "DDL_STATEMENTS",
]
