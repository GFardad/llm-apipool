"""Extended CLI tests for uncovered code paths in cli.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from llm_keypool.cli import app, _load_provider_configs

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own DB via env var."""
    db = tmp_path / "cli_ext_test.db"
    monkeypatch.setenv("LLM_KEYPOOL_DB", str(db))
    yield db


# ===================================================================
# _load_provider_configs error handling
# ===================================================================


def test_load_provider_configs_file_not_found():
    """Config file missing raises typer.Exit (lines 40-41).

    We test this through the CLI runner because patching pathlib.Path.exists
    is unreliable (C extension type). The 'providers' command calls
    _load_provider_configs and has no DB dependency.
    """
    class _FakePath:
        def __init__(self, *args, **kwargs):
            pass
        def __truediv__(self, other):
            return _FakePath()
        def __str__(self):
            return "/fake/config/path"
        def __repr__(self):
            return "/fake/config/path"
        def exists(self):
            return False
        def open(self, *args, **kwargs):
            raise FileNotFoundError
        @property
        def parent(self):
            return _FakePath()

    with patch("llm_keypool.cli.Path", _FakePath):
        result = runner.invoke(app, ["providers"])
        assert result.exit_code != 0
        assert "Config file not found" in result.output


def test_load_provider_configs_invalid_json():
    """Invalid JSON in config file raises typer.Exit (lines 45-47)."""
    with patch("llm_keypool.cli.json.load") as mock_load:
        mock_load.side_effect = json.JSONDecodeError("msg", "doc", 0)
        with pytest.raises(typer.Exit):
            _load_provider_configs()


def test_load_provider_configs_missing_providers_key():
    """Missing 'providers' key raises typer.Exit (lines 45-47)."""
    with patch("llm_keypool.cli.json.load", return_value={}):
        with pytest.raises(typer.Exit):
            _load_provider_configs()


# ===================================================================
# add command edge cases
# ===================================================================


def test_add_empty_provider():
    """Empty provider name prints error and exits (lines 113-114)."""
    result = runner.invoke(app, ["add", "--provider", "", "--key", "testkey"])
    assert result.exit_code != 0
    assert "Provider name cannot be empty" in result.output


def test_add_key_too_short():
    """Key shorter than MIN_KEY_LENGTH prints error and exits (lines 123-124)."""
    result = runner.invoke(app, ["add", "--provider", "groq", "--key", "ab"])
    assert result.exit_code != 0
    assert "API key too short" in result.output


def test_add_unknown_capabilities_warning():
    """Unknown capability flags produce a warning (lines 131-132)."""
    result = runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_unknowncap",
        "--capabilities", "unknown_cap,another_unknown",
    ])
    assert result.exit_code == 0
    assert "Warning: unknown capabilities" in result.output
    assert "unknown_cap" in result.output


def test_add_with_base_url():
    """--base-url override is accepted and forwarded."""
    result = runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_baseurl",
        "--base-url", "https://custom.example.com/v1",
    ])
    assert result.exit_code == 0


def test_add_with_model_and_capabilities():
    """--model and multiple --capabilities work together."""
    result = runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_multi",
        "--capabilities", "general_purpose,fast",
        "--model", "llama-3.1-8b-instant",
    ])
    assert result.exit_code == 0
    assert "llama-3.1-8b-instant" in result.output


# ===================================================================
# deactivate edge cases
# ===================================================================


def test_deactivate_already_inactive():
    """Deactivating an already-inactive key prints warning (lines 162-163)."""
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_already_inactive"])
    result = runner.invoke(app, ["deactivate", "--id", "1"])
    assert result.exit_code == 0
    assert "deactivated" in result.output.lower()

    result = runner.invoke(app, ["deactivate", "--id", "1"])
    assert result.exit_code == 0
    assert "already inactive" in result.output.lower()


# ===================================================================
# audit command
# ===================================================================


def test_audit_empty():
    """Audit with no data shows 'No audit entries' (lines 238-245)."""
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_audit_empty"])
    result = runner.invoke(app, ["audit"])
    assert result.exit_code == 0
    assert "No audit entries" in result.output


def test_audit_with_subscriber_filter(tmp_path):
    """Audit with --subscriber filter (lines 238-245)."""
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_audit_sub"])
    result = runner.invoke(app, ["audit", "--subscriber", "nonexistent"])
    assert result.exit_code == 0
    assert "No audit entries" in result.output


def test_audit_summary_empty():
    """Audit --summary with no data shows message (lines 215-216)."""
    result = runner.invoke(app, ["audit", "--summary"])
    assert result.exit_code == 0
    assert "No audit data" in result.output


# ===================================================================
# gui command
# ===================================================================


def test_gui_import_error(monkeypatch):
    """gui command with missing textual shows error and exits (lines 277-282)."""
    import builtins as _builtins
    import sys

    monkeypatch.delitem(sys.modules, "llm_keypool.tui", raising=False)

    real_import = _builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "llm_keypool.tui":
            raise ImportError("No module named llm_keypool.tui")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", mock_import)
    result = runner.invoke(app, ["gui"])
    assert result.exit_code != 0
    assert "Textual not installed" in result.output


# ===================================================================
# proxy command edge cases
# ===================================================================


def test_proxy_import_error(monkeypatch):
    """proxy command with missing uvicorn/proxy shows error (lines 307-313)."""
    import builtins as _builtins

    real_import = _builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No uvicorn")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", mock_import)
    result = runner.invoke(app, ["proxy", "--port", "9999"])
    assert result.exit_code != 0
    assert "Proxy deps missing" in result.output


def test_proxy_quality_tier_exceeds_max():
    """proxy with quality-tier > max-fallback-tier shows error (lines 317-321)."""
    result = runner.invoke(app, [
        "proxy", "--quality-tier", "3", "--max-fallback-tier", "1",
    ])
    assert result.exit_code != 0
    assert "--quality-tier must be <= --max-fallback-tier" in result.output


# ===================================================================
# audit command with data (covers loops at lines 218-236, 247-271)
# ===================================================================


def test_audit_with_data(tmp_path, monkeypatch):
    """Audit with actual data shows table rows (lines 218-236, 247-271)."""
    db = tmp_path / "audit_data.db"
    monkeypatch.setenv("LLM_KEYPOOL_DB", str(db))
    from llm_keypool.key_store import KeyStore
    store = KeyStore()
    store.register_key("groq", "gsk_auditdata", "general_purpose", "llama-3.3-70b", {})
    keys = store.get_all_keys()
    key_id = keys[0]["id"]
    store.log_audit("subscriber_one", key_id, "groq", "llama-3.3-70b", tokens_in=10, tokens_out=20)
    store.log_audit("subscriber_two", key_id, "groq", "llama-3.3-70b", tokens_in=5, tokens_out=15)

    # Test detail audit (lines 247-271)
    result = runner.invoke(app, ["audit"])
    assert result.exit_code == 0
    assert "subscriber_one" in result.output
    assert "subscriber_two" in result.output
    assert "groq" in result.output

    # Test summary audit (lines 218-236)
    result2 = runner.invoke(app, ["audit", "--summary"])
    assert result2.exit_code == 0
    assert "subscriber_one" in result2.output
    assert "subscriber_two" in result2.output
    assert "30" in result2.output or "20" in result2.output  # total tokens


# ===================================================================
# gui command success path (covers line 282)
# ===================================================================


def test_gui_calls_run(monkeypatch):
    """gui command calls run() from tui module when available (line 282)."""
    import llm_keypool.tui
    mock_run = MagicMock()
    monkeypatch.setattr(llm_keypool.tui, "run", mock_run)
    result = runner.invoke(app, ["gui"])
    assert result.exit_code == 0
    mock_run.assert_called_once()


# ===================================================================
# proxy command success path (covers lines 323-331)
# ===================================================================


@patch("uvicorn.run")
@patch("llm_keypool.proxy.make_app")
def test_proxy_runs_uvicorn(mock_make_app, mock_uvicorn_run):
    """proxy command calls uvicorn.run with the app (lines 323-331)."""
    mock_make_app.return_value = "mock_app"
    result = runner.invoke(app, [
        "proxy", "--port", "9994", "--host", "127.0.0.1",
        "--capabilities", "fast,code",
    ])
    assert result.exit_code == 0
    mock_uvicorn_run.assert_called_once_with("mock_app", host="127.0.0.1", port=9994)
    assert mock_make_app.call_args.kwargs["capabilities"] == ["fast", "code"]


# ===================================================================
# import command edge cases
# ===================================================================


def test_import_oserror(tmp_path):
    """Import from a path that is a directory raises OSError (lines 624-626)."""
    result = runner.invoke(app, ["import", str(tmp_path)])
    assert result.exit_code != 0
    assert "Error reading file" in result.output


def test_import_unknown_provider_in_ndjson(tmp_path):
    """NDJSON entry with unknown provider reports error (lines 454-455)."""
    p = tmp_path / "unknown_prov.json"
    p.write_text(json.dumps({"key": "gsk_valid_key", "provider": "nonexistent"}))
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code != 0
    assert "Unknown provider" in result.output


def test_import_key_too_short(tmp_path):
    """Key shorter than MIN_KEY_LENGTH reports error (lines 458-459).

    Use a known-prefix key that is too short (sk- = 3 chars, min=4).
    """
    p = tmp_path / "short_key.txt"
    p.write_text("sk-")  # detected as openai, but length=3 < MIN_KEY_LENGTH=4
    result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code != 0
    assert "Key too short" in result.output


def test_import_capabilities_as_list_in_ndjson(tmp_path):
    """NDJSON with capabilities as list (line 467)."""
    p = tmp_path / "caps_list.json"
    p.write_text(json.dumps({"key": "gsk_listcap", "capabilities": ["code", "fast"]}))
    with patch("llm_keypool.key_store.KeyStore.register_key") as mock_reg:
        mock_reg.return_value = {"success": True, "message": "registered"}
        result = runner.invoke(app, ["import", str(p)])
    assert result.exit_code == 0
    assert mock_reg.call_args.kwargs["capabilities"] == ["code", "fast"]


def test_import_zero_success_with_force(tmp_path):
    """With --force and zero successes, exit code non-zero."""
    p = tmp_path / "all_fail.txt"
    p.write_text("gsk_valid_key1\ngsk_valid_key2")
    with patch("llm_keypool.key_store.KeyStore.register_key") as mock_reg:
        mock_reg.return_value = {"success": False, "message": "already registered"}
        result = runner.invoke(app, ["import", str(p), "--force"])
    assert result.exit_code != 0
    assert "No keys were imported successfully" in result.output
