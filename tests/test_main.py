"""Tests for __main__.py entry point.

Covers lines 3-12 of __main__.py.
"""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch


def test_main_calls_app():
    """main() should invoke the CLI app (covers lines 6-9)."""
    from llm_keypool.__main__ import main

    with patch("llm_keypool.__main__.app") as mock_app:
        main()
        mock_app.assert_called_once()


def test_module_imports():
    """Importing __main__ module executes without error (covers line 3)."""
    import llm_keypool.__main__ as m  # noqa: F811

    assert m is not None
    assert hasattr(m, "main")
    assert hasattr(m, "app")


def test_direct_invocation():
    """Running python -m llm_keypool triggers __name__ == '__main__' branch (line 12).

    We run --help to get clean exit rather than opening the interactive CLI.
    """
    result = subprocess.run(
        [sys.executable, "-m", "llm_keypool", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "llm-keypool" in result.stdout.lower()
