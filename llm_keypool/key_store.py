"""SQLite-backed key store for llm-keypool."""

import contextlib
import json
import logging
import os
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MASK_MIN_LEN = 8
_MASK_SHOW = 4


def _mask_key(api_key: str) -> str:
    """Mask an API key for safe logging: show last 4 chars only."""
    if len(api_key) <= _MASK_MIN_LEN:
        return "****" + api_key[-_MASK_SHOW:] if len(api_key) > _MASK_SHOW else "****"
    return api_key[:_MASK_SHOW] + "****" + api_key[-_MASK_SHOW:]


# DB lives at ~/.llm-keypool/keys.db by default; override via LLM_KEYPOOL_DB env var
_NEW_DB_DEFAULT = Path.home() / ".llm-keypool" / "keys.db"
_OLD_DB_DEFAULT = Path.home() / ".llm-aggregator" / "keys.db"

def _resolve_db_path() -> Path:
    env = os.environ.get("LLM_KEYPOOL_DB") or os.environ.get("LLM_AGGREGATOR_DB")
    if env:
        return Path(env)
    if _NEW_DB_DEFAULT.exists() and _OLD_DB_DEFAULT.exists():
        logger.warning(
            "Both %s and %s exist. Using %s.",
            _OLD_DB_DEFAULT, _NEW_DB_DEFAULT, _NEW_DB_DEFAULT,
        )
    if not _NEW_DB_DEFAULT.exists() and _OLD_DB_DEFAULT.exists():
        _NEW_DB_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_OLD_DB_DEFAULT, _NEW_DB_DEFAULT)
    return _NEW_DB_DEFAULT

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    api_key TEXT NOT NULL,
    base_url_override TEXT,
    capabilities TEXT NOT NULL DEFAULT '["general_purpose"]',
    model TEXT,
    extra_params TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    tokens_used_today INTEGER NOT NULL DEFAULT 0,
    tokens_used_month INTEGER NOT NULL DEFAULT 0,
    requests_today INTEGER NOT NULL DEFAULT 0,
    requests_month INTEGER NOT NULL DEFAULT 0,
    last_429_at TEXT,
    cooldown_until TEXT,
    daily_reset_date TEXT,
    monthly_reset_month TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    UNIQUE(provider, api_key)
);

CREATE TABLE IF NOT EXISTS rotation_state (
    cap_key TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rotation_slot_counts (
    key_id INTEGER NOT NULL PRIMARY KEY,
    slot_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    subscriber_id TEXT NOT NULL DEFAULT 'unknown',
    key_id        INTEGER,
    provider      TEXT,
    model         TEXT,
    tokens_in     INTEGER DEFAULT 0,
    tokens_out    INTEGER DEFAULT 0,
    latency_ms    INTEGER DEFAULT 0,
    success       INTEGER DEFAULT 1,
    error         TEXT
);
"""

# Performance indexes for frequently queried columns
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider)",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_cooldown ON api_keys(cooldown_until)",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_requests_today ON api_keys(requests_today)",
    "CREATE INDEX IF NOT EXISTS idx_rotation_state_cap_key ON rotation_state(cap_key)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_subscriber ON audit_log(subscriber_id)",
]

MIGRATIONS = [
    "ALTER TABLE api_keys ADD COLUMN model TEXT",
    # capabilities column: migrate from legacy category column
    "ALTER TABLE api_keys ADD COLUMN capabilities TEXT",
    # rotation_state: rename category -> cap_key (SQLite 3.25+)
    "ALTER TABLE rotation_state RENAME COLUMN category TO cap_key",
    # audit_log table
    (
        "CREATE TABLE IF NOT EXISTS audit_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts TEXT NOT NULL, "
        "subscriber_id TEXT NOT NULL DEFAULT 'unknown', "
        "key_id INTEGER, "
        "provider TEXT, "
        "model TEXT, "
        "tokens_in INTEGER DEFAULT 0, "
        "tokens_out INTEGER DEFAULT 0, "
        "latency_ms INTEGER DEFAULT 0, "
        "success INTEGER DEFAULT 1, "
        "error TEXT)"
    ),
    "ALTER TABLE api_keys ADD COLUMN base_url_override TEXT",
]


class KeyStore:
    """SQLite-backed persistent key store."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the key store."""
        self._db_path = db_path or _resolve_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            for migration in MIGRATIONS:
                try:
                    conn.execute(migration)
                except sqlite3.OperationalError as e:
                    logger.debug("Migration skipped (already applied): %s", e)
            for index in INDEXES:
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(index)

    # --- capability helpers ---

    @staticmethod
    def parse_capabilities(row: dict[str, Any]) -> list[str]:
        """Parse capabilities from a DB row."""
        caps = row.get("capabilities")
        if caps:
            try:
                parsed = json.loads(caps)
                if isinstance(parsed, list) and parsed:
                    return [str(c) for c in parsed]
            except (json.JSONDecodeError, TypeError):
                return [str(caps)]
        return ["general_purpose"]

    # --- key management ---

    def register_key(  # noqa: PLR0913
        self,
        provider: str,
        api_key: str,
        capabilities: list[str] | str | None = None,
        model: str | None = None,
        base_url_override: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a new API key in the store."""
        if capabilities is None:
            capabilities = ["general_purpose"]
        elif isinstance(capabilities, str):
            # backward compat: positional string arg (old category param)
            capabilities = [capabilities]
        with self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO api_keys (provider, api_key, base_url_override, capabilities, model, extra_params) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        provider,
                        api_key,
                        base_url_override or None,
                        json.dumps(capabilities),
                        model or None,
                        json.dumps(extra_params or {}),
                    ),
                )
            except sqlite3.IntegrityError:
                return {
                    "success": False,
                    "message": f"Key already registered for {provider}. Deactivate existing key first.",
                }
            else:
                caps_str = ", ".join(capabilities)
                return {
                    "success": True,
                    "message": f"Key registered for {provider} ({caps_str}) model={model or 'default'}",
                }

    def get_active_keys(self, capabilities: list[str] | str) -> list[dict[str, Any]]:
        """Return active, non-cooled-down keys that have ANY of the requested capabilities."""
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM api_keys
                   WHERE is_active = 1
                     AND (cooldown_until IS NULL OR cooldown_until < ?)
                   ORDER BY requests_today ASC""",
                (now,),
            ).fetchall()
        result = []
        for r in rows:
            row = dict(r)
            key_caps = self.parse_capabilities(row)
            if any(c in key_caps for c in capabilities):
                result.append(row)
        return result

    def get_all_keys(self) -> list[dict[str, Any]]:
        """Return all registered keys."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM api_keys ORDER BY provider").fetchall()
            return [dict(r) for r in rows]

    def get_key_by_id(self, key_id: int) -> dict[str, Any] | None:
        """Return a key by its ID, or None if not found."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
            return dict(row) if row else None

    def record_usage(self, key_id: int, tokens: int, was_429: bool, cooldown_until: str | None = None) -> None:  # noqa: FBT001
        """Record token usage for a key and update counters."""
        now = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        month = datetime.now(UTC).strftime("%Y-%m")

        with self._conn() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
            if not row:
                return
            row = dict(row)

            tokens_today   = row["tokens_used_today"] if row["daily_reset_date"] == today else 0
            requests_today = row["requests_today"]    if row["daily_reset_date"] == today else 0
            tokens_month   = row["tokens_used_month"] if row["monthly_reset_month"] == month else 0
            requests_month = row["requests_month"]    if row["monthly_reset_month"] == month else 0

            conn.execute(
                """UPDATE api_keys SET
                    tokens_used_today   = ?,
                    tokens_used_month   = ?,
                    requests_today      = ?,
                    requests_month      = ?,
                    last_used_at        = ?,
                    last_429_at         = CASE WHEN ? THEN ? ELSE last_429_at END,
                    cooldown_until      = ?,
                    daily_reset_date    = ?,
                    monthly_reset_month = ?
                WHERE id = ?""",
                (
                    tokens_today + tokens, tokens_month + tokens,
                    requests_today + 1,    requests_month + 1,
                    now,
                    was_429, now if was_429 else None,
                    cooldown_until,
                    today, month,
                    key_id,
                ),
            )

    def update_key(self, key_id: int, model: str | None = None, api_key: str | None = None) -> bool:
        """Update a key's model and/or api_key by ID. Returns True if updated."""
        if model is None and api_key is None:
            return False
        with self._conn() as conn:
            if model is not None:
                conn.execute("UPDATE api_keys SET model = ? WHERE id = ?", (model or None, key_id))
            if api_key is not None:
                conn.execute("UPDATE api_keys SET api_key = ? WHERE id = ?", (api_key, key_id))
        return True

    def deactivate_key(self, key_id: int) -> None:
        """Deactivate a key (soft delete)."""
        with self._conn() as conn:
            conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))

    def clear_cooldown(self, key_id: int) -> None:
        """Clear a key's cooldown (after quota reset)."""
        with self._conn() as conn:
            conn.execute("UPDATE api_keys SET cooldown_until = NULL WHERE id = ?", (key_id,))

    # --- audit log ---

    def log_audit(  # noqa: PLR0913
        self,
        subscriber_id: str,
        key_id: int,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        success: bool = True,  # noqa: FBT001, FBT002
        error: str | None = None,
    ) -> None:
        """Log an API call to the audit trail."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO audit_log
                   (ts, subscriber_id, key_id, provider, model, tokens_in, tokens_out, latency_ms, success, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, subscriber_id, key_id, provider, model, tokens_in, tokens_out, latency_ms,
                 1 if success else 0, error),
            )

    def get_audit_log(
        self,
        subscriber_id: str | None = None,
        days: int = 7,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return audit log entries, optionally filtered by subscriber."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            if subscriber_id:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE ts > ? AND subscriber_id = ? ORDER BY ts DESC LIMIT ?",
                    (cutoff, subscriber_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE ts > ? ORDER BY ts DESC LIMIT ?",
                    (cutoff, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_audit_summary(self, days: int = 7) -> list[dict[str, Any]]:
        """Aggregate token/request counts grouped by subscriber_id."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT subscriber_id,
                          COUNT(*) as requests,
                          SUM(tokens_in) as tokens_in,
                          SUM(tokens_out) as tokens_out,
                          SUM(tokens_in + tokens_out) as tokens_total,
                          SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors
                   FROM audit_log
                   WHERE ts > ?
                   GROUP BY subscriber_id
                   ORDER BY tokens_total DESC""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- rotation state persistence ---

    def save_rotation_state(self, cap_key: str, cursor: int, slot_counts: dict[int, int]) -> None:
        """Persist rotation state for a capabilities group."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rotation_state (cap_key, cursor, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(cap_key) DO UPDATE SET cursor=excluded.cursor, updated_at=excluded.updated_at",
                (cap_key, cursor, now),
            )
            for key_id, count in slot_counts.items():
                conn.execute(
                    "INSERT INTO rotation_slot_counts (key_id, slot_count) VALUES (?, ?) "
                    "ON CONFLICT(key_id) DO UPDATE SET slot_count=excluded.slot_count",
                    (key_id, count),
                )

    def load_rotation_state(self, cap_key: str) -> tuple[int, dict[int, int]]:
        """Load rotation state for a capabilities group."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cursor FROM rotation_state WHERE cap_key = ?", (cap_key,),
            ).fetchone()
            cursor = row["cursor"] if row else 0

            rows = conn.execute("SELECT key_id, slot_count FROM rotation_slot_counts").fetchall()
            slot_counts = {r["key_id"]: r["slot_count"] for r in rows}

        return cursor, slot_counts
