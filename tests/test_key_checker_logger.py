"""Tests for key_checker.py error classification."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from llm_apipool.providers.base import CompletionResult


@pytest.mark.asyncio
class TestCheckKeyErrorClassification:
    """check_key_against_provider classifies errors for better UX."""

    @patch("llm_apipool.key_checker._call_provider")
    async def test_401_reported_as_invalid_key(self, mock_call: AsyncMock) -> None:
        mock_call.return_value = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="HTTP 401 from provider google: Unauthorized",
        )
        from llm_apipool.key_checker import check_key_against_provider

        provider, ok, msg = await check_key_against_provider(
            "google", "sk-bad", configs=_cfg()
        )
        assert ok is False
        assert "invalid key" in msg

    @patch("llm_apipool.key_checker._call_provider")
    async def test_403_reported_as_access_denied(self, mock_call: AsyncMock) -> None:
        mock_call.return_value = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="HTTP 403: Access denied. The model is not available.",
        )
        from llm_apipool.key_checker import check_key_against_provider

        provider, ok, msg = await check_key_against_provider(
            "google", "sk-valid", configs=_cfg()
        )
        assert ok is False
        assert "access denied" in msg
        assert "model restricted" in msg

    @patch("llm_apipool.key_checker._call_provider")
    async def test_429_reported_as_rate_limited(self, mock_call: AsyncMock) -> None:
        mock_call.return_value = CompletionResult(
            text="",
            tokens_used=0,
            was_429=True,
            error="Rate limited (429): Too Many Requests",
        )
        from llm_apipool.key_checker import check_key_against_provider

        provider, ok, msg = await check_key_against_provider(
            "groq", "sk-valid", configs=_cfg()
        )
        assert ok is False
        assert "rate limited" in msg
        assert "key likely valid" in msg

    @patch("llm_apipool.key_checker._call_provider")
    async def test_success_returns_ok(self, mock_call: AsyncMock) -> None:
        mock_call.return_value = CompletionResult(
            text="This is a test response",
            tokens_used=5,
            was_429=False,
        )

        # Need to mock load_provider_configs too since check_key_against_provider
        # calls it when configs is provided
        from llm_apipool.key_checker import check_key_against_provider

        provider, ok, msg = await check_key_against_provider(
            "groq", "sk-valid", configs=_cfg()
        )
        assert ok is True

    @patch("llm_apipool.key_checker._call_provider")
    async def test_generic_error_passthrough(self, mock_call: AsyncMock) -> None:
        mock_call.return_value = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="Connection error: timed out",
        )
        from llm_apipool.key_checker import check_key_against_provider

        provider, ok, msg = await check_key_against_provider(
            "groq", "sk-test", configs=_cfg()
        )
        assert ok is False
        assert "Connection error" in msg


def _cfg() -> dict:
    """Return a minimal provider config for testing."""
    return {
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "openai_compatible": True,
            "default_model": "llama-3.3-70b-versatile",
            "no_auth": False,
            "capabilities": ["general_purpose"],
        },
        "google": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "openai_compatible": True,
            "default_model": "gemini-2.0-flash",
            "no_auth": False,
            "capabilities": ["general_purpose"],
        },
    }
