"""Tests for CLI commands via Typer test runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from llm_keypool.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own DB via env var."""
    db = tmp_path / "cli_test.db"
    monkeypatch.setenv("LLM_KEYPOOL_DB", str(db))
    yield db


def test_status_empty():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "No keys registered" in result.output


def test_add_key_success():
    result = runner.invoke(app, [
        "add",
        "--provider", "groq",
        "--key", "gsk_testkey123",
        "--capabilities", "general_purpose",
    ])
    assert result.exit_code == 0
    assert "groq" in result.output




def test_add_key_unknown_provider():
    result = runner.invoke(app, [
        "add",
        "--provider", "unknown_provider_xyz",
        "--key", "some_key",
    ])
    assert result.exit_code != 0
    assert "unknown" in result.output.lower() or "Unknown" in result.output


def test_add_key_then_status_shows_it():
    runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_test",
    ])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "groq" in result.output


def test_add_key_with_model():
    result = runner.invoke(app, [
        "add",
        "--provider", "groq",
        "--key", "gsk_testkey",
        "--model", "llama-3.1-8b-instant",
    ])
    assert result.exit_code == 0


def test_add_duplicate_key_fails():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_same"])
    result = runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_same"])
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_deactivate_key():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_deact_test"])
    result = runner.invoke(app, ["deactivate", "--id", "1"])
    assert result.exit_code == 0
    assert "deactivated" in result.output.lower()


def test_deactivate_nonexistent_key():
    result = runner.invoke(app, ["deactivate", "--id", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_clear_cooldown():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_cooldown_test"])
    result = runner.invoke(app, ["clear-cooldown", "--id", "1"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_clear_cooldown_nonexistent():
    result = runner.invoke(app, ["clear-cooldown", "--id", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_providers_lists_known_providers():
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    for p in ["groq", "mistral", "openrouter", "cohere"]:
        assert p in result.output


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "llm-keypool" in result.output.lower() or "key pool" in result.output.lower()


def test_status_shows_registered_key_details():
    runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_status_test",
        "--model", "llama-3.3-70b-versatile",
    ])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "llama-3.3-70b" in result.output  # Rich may truncate long model names in table


# ===================================================================
# Import command tests
# ===================================================================


def _import_file(lines: list[str], tmp_path: Path, name: str = "import_keys.txt") -> Path:
    """Write lines to a temp import file and return its path."""
    path = tmp_path / name
    path.write_text("\n".join(lines))
    return path


# -------------------------------------------------------------------
# File-level errors
# -------------------------------------------------------------------


def test_import_file_not_found():
    """Import of a non-existent file exits with error."""
    result = runner.invoke(app, ["import", "/nonexistent/keys.txt"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_import_empty_file(tmp_path):
    """Import of an empty file prints a message and exits cleanly."""
    p = _import_file([], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert "empty" in result.output.lower()


def test_import_only_comments(tmp_path):
    """File with only comments yields no keys found."""
    p = _import_file(["# comment one", "# comment two"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert "No keys found" in result.output


def test_import_only_block_separators(tmp_path):
    """File with only block separators yields no keys found."""
    p = _import_file(["---", "---"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert "No keys found" in result.output


# -------------------------------------------------------------------
# Dry-run mode – parse & display without registration
# -------------------------------------------------------------------


def test_import_dry_run_key_per_line(tmp_path):
    """Key-per-line format is parsed correctly in dry-run mode."""
    p = _import_file(["gsk_testkey12345", "sk-testkey12345", "cs_testkey12345"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "Dry-run" in result.output
    assert "groq" in result.output
    assert "openai" in result.output
    assert "cerebras" in result.output


def test_import_dry_run_provider_key_format(tmp_path):
    """provider:key format is parsed correctly in dry-run."""
    p = _import_file(["groq:gsk_testkey12345", "openai:sk-testkey12345"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "openai" in result.output


def test_import_dry_run_ndjson(tmp_path):
    """NDJSON entries are parsed correctly in dry-run."""
    entry = json.dumps({
        "key": "gsk_testkey12345",
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
    })
    p = _import_file([entry], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "llama-3.1-8b-instant" in result.output


def test_import_dry_run_block_separated(tmp_path):
    """Block-separated content is handled in dry-run."""
    p = _import_file(["gsk_key1", "---", "sk-key2", "---", "cs_key3"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "openai" in result.output
    assert "cerebras" in result.output


def test_import_dry_run_mixed_formats(tmp_path):
    """Mixed formats (key-per-line, provider:key, NDJSON) all work together."""
    ndjson = json.dumps({"key": "mi_testkey12345", "model": "mistral-large"})
    lines = [
        "gsk_testkey12345",          # key-per-line     → groq
        "openai:sk-testkey12345",     # provider:key     → openai
        ndjson,                       # NDJSON            → mistral
        "---",                        # separator
        "cs_testkey12345",            # key-per-line     → cerebras
    ]
    p = _import_file(lines, tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "openai" in result.output
    assert "mistral" in result.output
    assert "cerebras" in result.output


def test_import_dry_run_no_detectable_prefix(tmp_path):
    """Unknown key prefix shows appropriate error in dry-run."""
    p = _import_file(["zzz_unknown_key"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "Cannot detect provider" in result.output


def test_import_dry_run_ndjson_invalid_json(tmp_path):
    """Invalid JSON lines are reported without crashing."""
    p = _import_file(["{bad json}"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "Invalid JSON" in result.output


def test_import_dry_run_ndjson_missing_key(tmp_path):
    """NDJSON entry without a 'key' field is reported."""
    p = _import_file([json.dumps({"provider": "groq"})], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "missing" in result.output.lower()


def test_import_dry_run_provider_key_unknown_provider(tmp_path):
    """provider:key with unknown provider can't be detected (key includes the colon prefix)."""
    p = _import_file(["nonexistent_provider:gsk_testkey12345"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "Cannot detect provider" in result.output


def test_import_dry_run_whitespace_and_comments_skipped(tmp_path):
    """Blank lines, comments, and separators are ignored during parsing."""
    lines = [
        "",
        "   ",
        "# comment",
        "gsk_key1",
        "---",
        "# another comment",
        "",
        "sk-key2",
    ]
    p = _import_file(lines, tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "openai" in result.output


# -------------------------------------------------------------------
# Auto-detection of key prefixes
# -------------------------------------------------------------------


@pytest.mark.parametrize("prefix,provider,suffix", [
    ("gsk_", "groq", "testkey"),
    ("sk-", "openai", "testkey"),
    ("cs_", "cerebras", "testkey"),
    ("mi_", "mistral", "testkey"),
    ("AIza", "google", "testkey"),
    ("hf_", "huggingface_router", "testkey"),
    ("or_", "openrouter", "testkey"),
    ("cohere_", "cohere", "testkey"),
    ("cf-", "cloudflare", "testkey"),
])
def test_import_auto_detect_prefix(tmp_path, prefix, provider, suffix):
    """Every known key prefix auto-detects to the correct provider."""
    key = f"{prefix}{suffix}"
    p = _import_file([key], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--dry-run"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert provider in result.output


# -------------------------------------------------------------------
# Registration with mocked KeyStore.register_key
# -------------------------------------------------------------------


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_registers_key(mock_register, tmp_path):
    """Import registers keys via KeyStore.register_key for each entry."""
    mock_register.return_value = {"success": True, "message": "Key registered for groq"}
    p = _import_file(["gsk_testregisterkey"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    mock_register.assert_called_once()
    assert mock_register.call_args.kwargs["provider"] == "groq"
    assert mock_register.call_args.kwargs["api_key"] == "gsk_testregisterkey"
    assert mock_register.call_args.kwargs["capabilities"] == ["general_purpose"]


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_registers_multiple_keys(mock_register, tmp_path):
    """Import with multiple keys calls register_key once per entry."""
    mock_register.return_value = {"success": True, "message": "Key registered"}
    p = _import_file(["gsk_key1", "gsk_key2", "sk-key3"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert mock_register.call_count == 3


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_summary_shown(mock_register, tmp_path):
    """Successful import displays an import summary block."""
    mock_register.return_value = {"success": True, "message": "Key registered"}
    p = _import_file(["gsk_key1", "gsk_key2"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert "Import Summary" in result.output


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_with_model_from_ndjson(mock_register, tmp_path):
    """NDJSON with model field passes model through to register_key."""
    mock_register.return_value = {"success": True, "message": "Key registered"}
    entry = json.dumps({"key": "gsk_ndjsonmodel", "model": "llama-3.1-8b-instant"})
    p = _import_file([entry], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert mock_register.call_args.kwargs["model"] == "llama-3.1-8b-instant"


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_with_capabilities_from_ndjson(mock_register, tmp_path):
    """NDJSON with capabilities field passes them through to register_key."""
    mock_register.return_value = {"success": True, "message": "Key registered"}
    entry = json.dumps({"key": "gsk_ndjsoncap", "capabilities": "code,fast"})
    p = _import_file([entry], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert mock_register.call_args.kwargs["capabilities"] == ["code", "fast"]


# -------------------------------------------------------------------
# --force / error-propagation behavior
# -------------------------------------------------------------------


def test_import_without_force_stops_on_detection_error(tmp_path):
    """Without --force, a detection error aborts the import."""
    p = _import_file(["gsk_validkey", "zzz_unknown"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code != 0
    assert "Aborting" in result.output


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_force_continues_on_detection_error(mock_register, tmp_path):
    """With --force, detection errors are warned but import continues."""
    mock_register.return_value = {"success": True, "message": "Key registered"}
    p = _import_file(["gsk_validkey", "zzz_unknown"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--force"])
    assert result.exit_code == 0
    mock_register.assert_called_once()  # only the valid key was registered


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_without_force_stops_on_registration_error(mock_register, tmp_path):
    """Without --force, a registration failure aborts the import."""
    mock_register.side_effect = [
        {"success": True, "message": "Key 1 registered"},
        {"success": False, "message": "Duplicate key"},
    ]
    p = _import_file(["gsk_key1", "gsk_key2"], tmp_path)
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code != 0
    assert "Aborting" in result.output


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_force_continues_on_registration_error(mock_register, tmp_path):
    """With --force, a registration failure is logged but import continues."""
    mock_register.side_effect = [
        {"success": True, "message": "Key 1 registered"},
        {"success": False, "message": "Duplicate key"},
        {"success": True, "message": "Key 3 registered"},
    ]
    p = _import_file(["gsk_key1", "gsk_key2", "gsk_key3"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--force"])
    assert result.exit_code == 0
    assert mock_register.call_count == 3
    assert "Failed" in result.output


@patch("llm_keypool.key_store.KeyStore.register_key")
def test_import_all_fail_with_force_exits_nonzero(mock_register, tmp_path):
    """With --force but zero successful registrations, exit code is non-zero."""
    mock_register.return_value = {"success": False, "message": "Duplicate key"}
    p = _import_file(["gsk_key1", "gsk_key2"], tmp_path)
    result = runner.invoke(app, ["import", str(p), "--force"])
    assert result.exit_code != 0
    assert "No keys were imported successfully" in result.output
