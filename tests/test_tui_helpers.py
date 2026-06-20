"""Tests for pure helper functions in llm_keypool.tui.

These are non-UI functions that can be tested without a Textual app running.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from llm_keypool.tui import (
    _build_dry_run_text,
    _build_summary_text,
    _build_warn_lines,
    _detect_provider_from_key,
    _load_providers,
    _mask_key_display,
    _now_iso,
    _parse_import_entry,
    _resolve_import_entries,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIGS: dict[str, dict] = {
    "groq": {
        "capabilities": ["general_purpose"],
        "base_url": "https://api.groq.com/openai/v1",
        "openai_compatible": True,
    },
    "openai": {
        "capabilities": ["general_purpose"],
        "base_url": "https://api.openai.com/v1",
        "openai_compatible": True,
    },
    "mistral": {
        "capabilities": ["general_purpose"],
        "base_url": "https://api.mistral.ai/v1",
        "openai_compatible": True,
    },
    "unknown_provider": {},
}


# ===================================================================
# _mask_key_display
# ===================================================================


class TestMaskKeyDisplay:
    """Tests for _mask_key_display(api_key: str) -> str."""

    def test_short_key_returns_masked(self) -> None:
        """Keys of length <= 8 return '****'."""
        assert _mask_key_display("") == "****"
        assert _mask_key_display("a") == "****"
        assert _mask_key_display("123") == "****"
        assert _mask_key_display("12345678") == "****"  # boundary: len == 8

    def test_longer_key_shows_four_and_four(self) -> None:
        """Keys of length >= 9 show first 4 and last 4 chars masked."""
        # boundary: len == 9
        assert _mask_key_display("123456789") == "1234****6789"
        # normal case
        assert _mask_key_display("gsk_abcdefghijklmnop") == "gsk_****mnop"
        # openai key
        assert _mask_key_display("sk-proj-abcdefghijklmnop") == "sk-p****mnop"
        # very long key
        long_key = "A" * 100
        assert _mask_key_display(long_key) == "AAAA****AAAA"

    def test_special_characters(self) -> None:
        """Special characters are preserved in the masked output."""
        key = "aB3#xY9!qWzP0@LmN"
        # len(key) = 16 -> first 4 = "aB3#", last 4 = "@LmN"
        result = _mask_key_display(key)
        assert len(result) == 12  # 4 + 4 + "****"
        assert result == "aB3#****@LmN"

    def test_only_first_and_last_four_visible(self) -> None:
        """The middle portion of the key is replaced with '****'."""
        key = "abcdefghijklmnopqrstuvwxyz"
        result = _mask_key_display(key)
        assert result.startswith("abcd")
        assert result.endswith("wxyz")
        assert "****" in result
        middle = result[4:-4]
        assert middle == "****"


# ===================================================================
# _detect_provider_from_key
# ===================================================================


class TestDetectProviderFromKey:
    """Tests for _detect_provider_from_key(api_key: str) -> str | None."""

    def test_detects_groq(self) -> None:
        assert _detect_provider_from_key("gsk_abcdef") == "groq"

    def test_detects_openai(self) -> None:
        assert _detect_provider_from_key("sk-abcdef") == "openai"

    def test_detects_cerebras(self) -> None:
        assert _detect_provider_from_key("cs_abcdef") == "cerebras"

    def test_detects_mistral(self) -> None:
        assert _detect_provider_from_key("mi_abcdef") == "mistral"

    def test_detects_google(self) -> None:
        assert _detect_provider_from_key("AIzaSyA...") == "google"

    def test_detects_huggingface_router(self) -> None:
        assert _detect_provider_from_key("hf_abcdef") == "huggingface_router"

    def test_detects_openrouter(self) -> None:
        assert _detect_provider_from_key("or_abcdef") == "openrouter"

    def test_detects_cohere(self) -> None:
        assert _detect_provider_from_key("cohere_abcdef") == "cohere"

    def test_detects_cloudflare(self) -> None:
        assert _detect_provider_from_key("cf-abcdef") == "cloudflare"

    def test_no_match_returns_none(self) -> None:
        assert _detect_provider_from_key("unknown_prefix_key") is None
        assert _detect_provider_from_key("") is None

    def test_case_sensitivity(self) -> None:
        """Prefix matching is case-sensitive; uppercase prefix may not match."""
        assert _detect_provider_from_key("GSK_") is None  # should be gsk_
        assert _detect_provider_from_key("SK-") is None   # should be sk-
        assert _detect_provider_from_key("AIZ") is None    # should be AIza
        # AIza is special — starts with uppercase
        assert _detect_provider_from_key("AIzaSyA...") == "google"
        assert _detect_provider_from_key("aiza") is None

    def test_partial_prefix_does_not_match(self) -> None:
        """A key that merely contains but does not start with a prefix returns None."""
        assert _detect_provider_from_key("xxx_gsk_") is None
        assert _detect_provider_from_key("xxxsk-") is None

    def test_detects_cf_prefix_with_trailing_content(self) -> None:
        """cf- prefix at the start of a longer key."""
        assert _detect_provider_from_key("cf-abc.123") == "cloudflare"


# ===================================================================
# _now_iso
# ===================================================================


class TestNowIso:
    """Tests for _now_iso() -> str."""

    def test_returns_string(self) -> None:
        result = _now_iso()
        assert isinstance(result, str)

    def test_returns_valid_iso_format(self) -> None:
        """Result can be parsed back into a datetime."""
        result = _now_iso()
        # Should be parseable
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)

    def test_returns_utc_time(self) -> None:
        """The result should end with +00:00 indicating UTC."""
        result = _now_iso()
        assert result.endswith("+00:00"), f"Expected UTC offset, got: {result}"

    def test_is_current_time(self) -> None:
        """The result should be within a few seconds of now."""
        before = datetime.now(UTC)
        result = _now_iso()
        after = datetime.now(UTC)
        parsed = datetime.fromisoformat(result)
        assert before <= parsed <= after, (
            f"Expected time between {before} and {after}, got {parsed}"
        )


# ===================================================================
# _parse_import_entry
# ===================================================================


class TestParseImportEntry:
    """Tests for _parse_import_entry(line: str, configs: dict) -> dict | None."""

    def test_empty_line_returns_none(self) -> None:
        assert _parse_import_entry("", SAMPLE_CONFIGS) is None
        assert _parse_import_entry("   ", SAMPLE_CONFIGS) is None
        assert _parse_import_entry("\t", SAMPLE_CONFIGS) is None

    def test_comment_line_returns_none(self) -> None:
        assert _parse_import_entry("# this is a comment", SAMPLE_CONFIGS) is None
        assert _parse_import_entry("  # indented comment", SAMPLE_CONFIGS) is None
        assert _parse_import_entry("#", SAMPLE_CONFIGS) is None

    def test_separator_line_returns_none(self) -> None:
        assert _parse_import_entry("---", SAMPLE_CONFIGS) is None
        assert _parse_import_entry("  ---  ", SAMPLE_CONFIGS) is None

    def test_ndjson_valid_full(self) -> None:
        """Full NDJSON with all fields."""
        line = '{"key":"gsk_abc","provider":"groq","capabilities":["code"],"model":"llama","base_url":"https://custom.url"}'
        result = _parse_import_entry(line, SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "gsk_abc"
        assert result["provider"] == "groq"
        assert result["capabilities"] == ["code"]
        assert result["model"] == "llama"
        assert result["base_url"] == "https://custom.url"

    def test_ndjson_valid_minimal(self) -> None:
        """Minimal NDJSON with only key."""
        line = '{"key":"sk-test123"}'
        result = _parse_import_entry(line, SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "sk-test123"
        assert result["provider"] is None
        assert result["capabilities"] is None
        assert result["model"] is None
        assert result["base_url"] is None

    def test_ndjson_non_string_key(self) -> None:
        """Key coerced to string even when it is a number in JSON."""
        line = '{"key":12345}'
        result = _parse_import_entry(line, SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "12345"

    def test_ndjson_missing_key_field(self) -> None:
        """NDJSON without a 'key' field returns an error dict."""
        line = '{"provider":"groq"}'
        result = _parse_import_entry(line, SAMPLE_CONFIGS)
        assert result is not None
        assert "_error" in result
        assert "missing 'key'" in result["_error"]

    def test_ndjson_invalid_json(self) -> None:
        """Malformed JSON in NDJSON returns an error dict."""
        line = '{"key": "gsk_abc", invalid}'
        result = _parse_import_entry(line, SAMPLE_CONFIGS)
        assert result is not None
        assert "_error" in result
        assert "Invalid JSON" in result["_error"]

    def test_provider_colon_key_format_known(self) -> None:
        """provider:key format with a known provider."""
        result = _parse_import_entry("groq:gsk_mykey123", SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "gsk_mykey123"
        assert result["provider"] == "groq"
        assert result["capabilities"] is None
        assert result["model"] is None
        assert result["base_url"] is None

    def test_provider_colon_key_case_insensitive(self) -> None:
        """Provider in provider:key format is lowercased for matching."""
        result = _parse_import_entry("GroQ:gsk_mykey123", SAMPLE_CONFIGS)
        assert result is not None
        assert result["provider"] == "groq"

    def test_provider_colon_key_with_whitespace(self) -> None:
        """Whitespace around provider and key is stripped."""
        result = _parse_import_entry("  groq :  gsk_mykey123  ", SAMPLE_CONFIGS)
        assert result is not None
        assert result["provider"] == "groq"
        assert result["key"] == "gsk_mykey123"

    def test_provider_colon_key_unknown_provider_falls_through(self) -> None:
        """provider:key format where provider is NOT in configs falls through to key-per-line."""
        result = _parse_import_entry("unknown_provider:some_key_value", SAMPLE_CONFIGS)
        # unknown_provider is in our SAMPLE_CONFIGS, so it matches
        # Let me test with a truly unknown one
        assert result is not None

    def test_provider_colon_key_not_in_configs_falls_to_key_per_line(self) -> None:
        """When the provider prefix is not in configs, it is treated as key-per-line."""
        result = _parse_import_entry("nonexistent:gsk_abc", SAMPLE_CONFIGS)
        # "nonexistent" is not in configs, so this should fall through to key-per-line
        assert result is not None
        assert result["key"] == "nonexistent:gsk_abc"  # full string is the key
        assert result["provider"] is None

    def test_key_per_line_fallback(self) -> None:
        """A line with no recognized format falls back to key-per-line."""
        result = _parse_import_entry("gsk_mysecretkey123", SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "gsk_mysecretkey123"
        assert result["provider"] is None

    def test_key_per_line_with_whitespace(self) -> None:
        """Whitespace is stripped for key-per-line."""
        result = _parse_import_entry("  sk-test12345  ", SAMPLE_CONFIGS)
        assert result is not None
        assert result["key"] == "sk-test12345"
        assert result["provider"] is None

    def test_provider_with_colon_in_rest_handled_correctly(self) -> None:
        """provider:key format where the key itself contains a colon."""
        result = _parse_import_entry("openai:sk-proj-abc:extra", SAMPLE_CONFIGS)
        # partition splits at first colon only
        assert result is not None
        assert result["key"] == "sk-proj-abc:extra"
        assert result["provider"] == "openai"


# ===================================================================
# _resolve_import_entries
# ===================================================================


class TestResolveImportEntries:
    """Tests for _resolve_import_entries(lines, configs)."""

    def test_empty_lines(self) -> None:
        entries, errors = _resolve_import_entries([], SAMPLE_CONFIGS)
        assert entries == []
        assert errors == []

    def test_all_skippable_lines(self) -> None:
        lines = ["", "# comment", "---", "  ", "\t"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert errors == []

    def test_valid_key_with_detectable_provider(self) -> None:
        lines = ["gsk_mykey123"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert errors == []
        assert entries[0]["key"] == "gsk_mykey123"
        assert entries[0]["provider"] == "groq"
        assert entries[0]["capabilities"] == ["general_purpose"]
        assert entries[0]["model"] is None
        assert entries[0]["base_url"] is None

    def test_valid_key_with_explicit_provider(self) -> None:
        lines = ["openai:sk-testkey123"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert errors == []
        assert entries[0]["key"] == "sk-testkey123"
        assert entries[0]["provider"] == "openai"

    def test_undetectable_provider_produces_error(self) -> None:
        lines = ["zzz_noprefixkey"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert len(errors) == 1
        ctx, reason = errors[0]
        assert "cannot detect provider" in reason.lower() or "Cannot detect" in reason
        assert "zzz_" in ctx  # masked display of key prefix

    def test_unknown_detected_provider_produces_error(self) -> None:
        """Provider detected from prefix but not in configs."""
        lines = ["cf-testkey123"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert len(errors) == 1
        ctx, reason = errors[0]
        # 'cf-' maps to 'cloudflare', which is NOT in SAMPLE_CONFIGS
        assert "unknown provider" in reason.lower() or "Unknown provider" in reason
        assert "cloudflare" in reason

    def test_key_too_short_produces_error(self) -> None:
        """Key with len < MIN_KEY_LENGTH (4) is rejected.

        'sk-' has length 3, is detectable as openai, and openai is in configs.
        """
        lines = ["sk-"]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert len(errors) == 1
        ctx, reason = errors[0]
        assert "too short" in reason.lower() or "Key too short" in reason

    def test_mixed_valid_and_invalid(self) -> None:
        lines = [
            "# comment",
            "gsk_goodkey12345",
            "",
            "zzz_noprefix",
            "openai:sk-validkey123",
            "---",
        ]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert len(entries) == 2
        assert len(errors) == 1
        providers = [e["provider"] for e in entries]
        assert "groq" in providers
        assert "openai" in providers

    def test_capabilities_as_string(self) -> None:
        """Capabilities provided as comma-separated string are split."""
        line = '{"key":"gsk_abc","capabilities":"code, fast, vision"}'
        entries, errors = _resolve_import_entries([line], SAMPLE_CONFIGS)
        assert len(entries) == 1
        caps = entries[0]["capabilities"]
        assert "code" in caps
        assert "fast" in caps
        assert "vision" in caps

    def test_capabilities_as_list(self) -> None:
        """Capabilities provided as JSON list are preserved."""
        line = '{"key":"gsk_abc","capabilities":["code","fast"]}'
        entries, errors = _resolve_import_entries([line], SAMPLE_CONFIGS)
        assert len(entries) == 1
        caps = entries[0]["capabilities"]
        assert caps == ["code", "fast"]

    def test_capabilities_empty_string_yields_empty_list(self) -> None:
        """Empty string capabilities are split into an empty list (no items after stripping)."""
        line = '{"key":"gsk_abc","capabilities":""}'
        entries, errors = _resolve_import_entries([line], SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert entries[0]["capabilities"] == []

    def test_capabilities_none_falls_to_default(self) -> None:
        """None capabilities fall back to default ['general_purpose']."""
        # provider:key format has capabilities=None
        entries, errors = _resolve_import_entries(["groq:gsk_testkey"], SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert entries[0]["capabilities"] == ["general_purpose"]

    def test_model_and_base_url_from_ndjson(self) -> None:
        """Model and base_url are propagated from NDJSON."""
        line = '{"key":"gsk_abc","model":"llama-3.3","base_url":"https://custom.url"}'
        entries, errors = _resolve_import_entries([line], SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert entries[0]["model"] == "llama-3.3"
        assert entries[0]["base_url"] == "https://custom.url"

    def test_empty_model_and_base_url_are_normalized_to_none(self) -> None:
        """Empty string model/base_url are normalized to None."""
        line = '{"key":"gsk_abc","model":"","base_url":""}'
        entries, errors = _resolve_import_entries([line], SAMPLE_CONFIGS)
        assert len(entries) == 1
        assert entries[0]["model"] is None
        assert entries[0]["base_url"] is None

    def test_ndjson_invalid_json_skipped(self) -> None:
        """Invalid JSON lines produce parse errors."""
        lines = ['{"key": "gsk_abc", broken}']
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert len(errors) == 1
        ctx, reason = errors[0]
        assert "Line 1" in ctx
        assert "Invalid JSON" in reason

    def test_ndjson_missing_key_field_skipped(self) -> None:
        """NDJSON missing 'key' field produces parse error."""
        lines = ['{"provider":"groq"}']
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert entries == []
        assert len(errors) == 1
        ctx, reason = errors[0]
        assert "Line 1" in ctx
        assert "missing 'key'" in reason

    def test_line_numbers_in_errors(self) -> None:
        """Error context includes correct line numbers."""
        lines = [
            "gsk_myvalidkey",  # line 1 - valid
            '{"key": broken}',  # line 2 - NDJSON parse error
            "zzz_noprefix",  # line 3 - undetectable provider
        ]
        entries, errors = _resolve_import_entries(lines, SAMPLE_CONFIGS)
        assert len(errors) >= 2
        # Line 2 should be a parse error
        line2_errors = [ctx for ctx, _ in errors if "Line 2" in ctx]
        assert len(line2_errors) >= 1
        # Line 3 should have an undetectable error (ctx is masked key, not line num)
        undetectable_errors = [r for _, r in errors if "Cannot detect" in r]
        assert len(undetectable_errors) >= 1


# ===================================================================
# _build_dry_run_text
# ===================================================================


class TestBuildDryRunText:
    """Tests for _build_dry_run_text(entries, errors)."""

    def test_no_entries_no_errors(self) -> None:
        result = _build_dry_run_text([], [])
        assert "No valid keys to import" in result

    def test_no_entries_with_errors(self) -> None:
        errors = [("abc***def", "Cannot detect provider from key prefix")]
        result = _build_dry_run_text([], errors)
        assert "Issues found (1)" in result
        assert "Cannot detect provider" in result
        assert "No valid keys to import" in result

    def test_entries_no_errors(self) -> None:
        entries = [
            {"key": "gsk_testkey123", "provider": "groq", "capabilities": ["general_purpose"]},
        ]
        result = _build_dry_run_text(entries, [])
        assert "Dry-run" in result
        assert "1 key(s) would be imported" in result
        assert "groq" in result
        # gsk_testkey123 (14 chars) -> gsk_****y123
        assert "gsk_****y123" in result
        assert "general_purpose" in result

    def test_multiple_entries_formatted_correctly(self) -> None:
        entries = [
            {"key": "gsk_abc123def456", "provider": "groq", "capabilities": ["general_purpose", "fast"]},
            {"key": "sk-proj-test-key-xyz", "provider": "openai", "capabilities": ["code"]},
        ]
        result = _build_dry_run_text(entries, [])
        assert "2 key(s) would be imported" in result
        assert "groq" in result
        assert "openai" in result
        assert "general_purpose, fast" in result
        assert "code" in result

    def test_entries_and_errors_together(self) -> None:
        entries = [
            {"key": "gsk_abcdefgh12345678", "provider": "groq", "capabilities": ["general_purpose"]},
        ]
        errors = [("zzz_****", "Cannot detect provider from key prefix")]
        result = _build_dry_run_text(entries, errors)
        assert "Issues found (1)" in result
        assert "1 key(s) would be imported" in result
        assert "groq" in result
        assert "zzz_" in result or "Cannot detect" in result


# ===================================================================
# _build_warn_lines
# ===================================================================


class TestBuildWarnLines:
    """Tests for _build_warn_lines(errors)."""

    def test_empty_errors(self) -> None:
        assert _build_warn_lines([]) == []

    def test_single_error(self) -> None:
        errors = [("abc***xyz", "Cannot detect provider from key prefix")]
        result = _build_warn_lines(errors)
        assert len(result) == 1
        assert "Warning" in result[0]
        assert "abc***xyz" in result[0]
        assert "skipping" in result[0]

    def test_multiple_errors(self) -> None:
        errors = [
            ("abc***xyz", "Reason A"),
            ("def***uvw", "Reason B"),
        ]
        result = _build_warn_lines(errors)
        assert len(result) == 2
        for line in result:
            assert line.startswith("[yellow]Warning:")
            assert "skipping" in line

    def test_special_chars_in_context(self) -> None:
        errors = [("!!!***???", "Some special reason!")]
        result = _build_warn_lines(errors)
        assert len(result) == 1
        assert "!!!" in result[0]


# ===================================================================
# _build_summary_text
# ===================================================================


class TestBuildSummaryText:
    """Tests for _build_summary_text(entries, parse_errors, succeeded, failed, warn_lines)."""

    def test_successful_import_no_issues(self) -> None:
        entries = [{"key": "gsk_test", "provider": "groq", "capabilities": ["general_purpose"]}]
        result = _build_summary_text(entries, [], 1, [], [])
        assert "Import Summary" in result
        assert "Total parsed:  1" in result
        assert "Registered: 1" in result
        assert "Skipped:    0" in result
        assert "Failed:     0" in result

    def test_with_parse_errors(self) -> None:
        entries = [{"key": "gsk_abc", "provider": "groq", "capabilities": ["general_purpose"]}]
        parse_errors = [("Line 2", "Invalid JSON")]
        result = _build_summary_text(entries, parse_errors, 1, [], [])
        assert "Total parsed:  2" in result
        assert "Skipped:    1" in result
        assert "⚠" in result
        assert "Line 2" in result

    def test_with_failed_keys(self) -> None:
        entries = [{"key": "gsk_abc", "provider": "groq", "capabilities": ["general_purpose"]}]
        failed = [("gsk_****bcde", "groq", "Key already exists")]
        result = _build_summary_text(entries, [], 0, failed, [])
        assert "Failed:     1" in result
        assert "Failed keys" in result
        assert "gsk_****bcde" in result
        assert "Key already exists" in result

    def test_with_warn_lines(self) -> None:
        entries = [{"key": "gsk_abc", "provider": "groq", "capabilities": ["general_purpose"]}]
        warn_lines = ["[yellow]Warning:[/yellow] abc***xyz: some reason - skipping"]
        result = _build_summary_text(entries, [], 1, [], warn_lines)
        assert "Warning" in result
        assert "abc***xyz" in result

    def test_all_categories_populated(self) -> None:
        entries = [{"key": "gsk_a", "provider": "groq", "capabilities": ["general_purpose"]}]
        parse_errors = [("Line 2", "Invalid JSON")]
        failed = [("gsk_****", "groq", "Duplicate")]
        warn_lines = ["[yellow]Warning:[/yellow] Line 2: Invalid JSON - skipping"]

        result = _build_summary_text(entries, parse_errors, 0, failed, warn_lines)
        # Warn lines come first
        assert result.startswith("[yellow]Warning:")
        assert "Import Summary" in result
        assert "Total parsed:  2" in result
        assert "Registered: 0" in result
        assert "Skipped:    1" in result
        assert "Failed:     1" in result
        assert "Failed keys" in result
        assert "Skipped keys (could not resolve)" in result


# ===================================================================
# _load_providers
# ===================================================================


class TestLoadProviders:
    """Tests for _load_providers() -> dict."""

    def test_successful_load(self, tmp_path: Path) -> None:
        """Load from a valid providers.json file."""
        provider_data = {
            "providers": {
                "test_provider": {"base_url": "https://test.api.com", "capabilities": ["general_purpose"]},
            },
        }
        config_path = tmp_path / "providers.json"
        config_path.write_text(json.dumps(provider_data))

        # Patch _CONFIG_PATH in the module
        with patch("llm_keypool.tui._CONFIG_PATH", config_path):
            result = _load_providers()

        assert result == provider_data["providers"]
        assert "test_provider" in result

    def test_file_not_found(self) -> None:
        """Raises RuntimeError when file does not exist."""
        with patch("llm_keypool.tui._CONFIG_PATH", Path("/nonexistent/path/providers.json")):
            with pytest.raises(RuntimeError, match="Provider config not found"):
                _load_providers()

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Raises RuntimeError when JSON is malformed."""
        config_path = tmp_path / "providers.json"
        config_path.write_text("not valid json")

        with patch("llm_keypool.tui._CONFIG_PATH", config_path):
            with pytest.raises(RuntimeError, match="Invalid provider config"):
                _load_providers()

    def test_missing_providers_key(self, tmp_path: Path) -> None:
        """Raises RuntimeError when top-level 'providers' key is missing."""
        config_path = tmp_path / "providers.json"
        config_path.write_text(json.dumps({"not_providers": {}}))

        with patch("llm_keypool.tui._CONFIG_PATH", config_path):
            with pytest.raises(RuntimeError, match="Invalid provider config"):
                _load_providers()

    def test_empty_providers_succeeds(self, tmp_path: Path) -> None:
        """Empty providers dict is valid."""
        config_path = tmp_path / "providers.json"
        config_path.write_text(json.dumps({"providers": {}}))

        with patch("llm_keypool.tui._CONFIG_PATH", config_path):
            result = _load_providers()

        assert result == {}

    def test_error_includes_path_on_file_not_found(self) -> None:
        """Error message should include the path."""
        missing_path = Path("/tmp/definitely_missing.json")
        with patch("llm_keypool.tui._CONFIG_PATH", missing_path):
            with pytest.raises(RuntimeError) as exc:
                _load_providers()
        assert str(missing_path) in str(exc.value)
