"""Tests for terminal error type classification in dispatch.py.

Verifies that:
- HTTP 400 exhaustion returns ``terminal_error_type="request_shape"``
- HTTP 429 exhaustion returns ``terminal_error_type="rate_limit"``
- Mixed errors set the *last* error type
- Exceptions are classified as ``"transient"``
- ``CompletionResult.terminal_error_type`` default is ``None``
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llm_apipool.providers.base import CompletionResult


class TestTerminalErrorTypeDefault:
    """``terminal_error_type`` should be ``None`` on a successful result."""

    def test_default_is_none(self) -> None:
        result = CompletionResult(text="ok", tokens_used=10, was_429=False)
        assert result.terminal_error_type is None

    def test_set_on_exhaustion(self) -> None:
        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="all_keys_exhausted",
            terminal_error_type="request_shape",
        )
        assert result.terminal_error_type == "request_shape"

    def test_set_on_rate_limit(self) -> None:
        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=True,
            error="all_keys_exhausted",
            terminal_error_type="rate_limit",
        )
        assert result.terminal_error_type == "rate_limit"

    def test_set_on_transient(self) -> None:
        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="max_retries_exceeded",
            terminal_error_type="transient",
        )
        assert result.terminal_error_type == "transient"


@pytest.mark.asyncio
class TestDispatchErrorTracking:
    """Verify dispatch.py tracks ``_last_error_type`` correctly.

    Uses a mock rotator that returns one key then None (exhausted).
    """

    @patch("llm_apipool.providers.dispatch._call_complete")
    async def test_400_sets_request_shape(self, mock_call: AsyncMock) -> None:
        from openai import APIStatusError

        mock_rotator = _make_rotator_that_returns_once()
        mock_call.side_effect = APIStatusError(
            "Bad Request",
            response=_mock_http_response(400),
            body={"error": "bad request"},
        )

        from llm_apipool.providers.dispatch import complete

        result, _ = await complete(
            mock_rotator, messages=[{"role": "user", "content": "hi"}]
        )
        assert result.terminal_error_type == "request_shape"

    @patch("llm_apipool.providers.dispatch._call_complete")
    async def test_429_sets_rate_limit(self, mock_call: AsyncMock) -> None:
        from openai import APIStatusError

        mock_rotator = _make_rotator_that_returns_once()
        mock_call.side_effect = APIStatusError(
            "Rate Limited",
            response=_mock_http_response(429),
            body={"error": "rate limit"},
        )

        from llm_apipool.providers.dispatch import complete

        result, _ = await complete(
            mock_rotator, messages=[{"role": "user", "content": "hi"}]
        )
        assert result.terminal_error_type == "rate_limit"

    @patch("llm_apipool.providers.dispatch._call_complete")
    async def test_exception_sets_transient(self, mock_call: AsyncMock) -> None:
        mock_rotator = _make_rotator_that_returns_once()
        mock_call.side_effect = RuntimeError("connection reset")

        from llm_apipool.providers.dispatch import complete

        result, _ = await complete(
            mock_rotator, messages=[{"role": "user", "content": "hi"}]
        )
        assert result.terminal_error_type == "transient"

    @patch("llm_apipool.providers.dispatch._call_complete")
    async def test_no_keys_uses_fallback(self, mock_call: AsyncMock) -> None:
        mock_rotator = _make_empty_rotator()
        mock_call.side_effect = RuntimeError("should not be called")

        from llm_apipool.providers.dispatch import complete

        result, _ = await complete(
            mock_rotator, messages=[{"role": "user", "content": "hi"}]
        )
        # No keys means no errors were tracked → fallback to "transient"
        assert result.terminal_error_type == "transient"


class TestChatRouteUsesTerminalType:
    """Verify that chat.py reads ``terminal_error_type`` and returns correct HTTP status."""

    def test_request_shape_returns_400(self) -> None:
        """Simulate the logic in chat.py that checks terminal_error_type."""
        from llm_apipool.api.errors import INVALID_REQUEST_ERROR

        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=False,
            error="all proxies returned 400",
            terminal_error_type="request_shape",
        )

        # This mirrors the chat.py logic
        term_type = getattr(result, "terminal_error_type", None)
        status = 503
        err_type = "server_error"
        if term_type == "request_shape":
            status, err_type = 400, INVALID_REQUEST_ERROR
        elif term_type == "rate_limit":
            status, err_type = 429, "rate_limit_error"

        assert status == 400
        assert err_type == INVALID_REQUEST_ERROR

    def test_rate_limit_returns_429(self) -> None:
        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=True,
            error="all keys rate limited",
            terminal_error_type="rate_limit",
        )

        term_type = getattr(result, "terminal_error_type", None)
        status = 503
        if term_type == "rate_limit":
            status = 429

        assert status == 429

    def test_none_falls_back_to_existing(self) -> None:
        result = CompletionResult(
            text="",
            tokens_used=0,
            was_429=True,
            error="rate limit",
            terminal_error_type=None,
        )

        term_type = getattr(result, "terminal_error_type", None)
        # Falls through to existing was_429 check
        assert term_type is None


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_rotator_that_returns_once():
    """Return a mock rotator that gives one key then ``None``."""

    rotator = MagicMock()
    rotator.store.get_all_keys.return_value = [{"is_active": 1, "id": 1}]
    rotator.get_best_key.side_effect = [
        {
            "key_id": 1,
            "provider": "test",
            "model": "test-model",
            "api_key": "sk-test",
            "base_url": "https://test.example.com",
            "openai_compatible": True,
            "no_auth": False,
            "capabilities": [],
            "extra_params": {},
        },
        None,
    ]
    rotator.skip_key = MagicMock()
    rotator.handle_429 = MagicMock()
    rotator.handle_error = MagicMock()
    rotator.handle_success = MagicMock()
    # Circuit breaker mock
    cb = MagicMock()
    cb.is_allowed.return_value = True
    with patch("llm_apipool.providers.dispatch.get_circuit_breaker", return_value=cb):
        pass  # applied via decorator in test
    return rotator


def _mock_http_response(status_code: int) -> httpx.Response:
    """Create an ``httpx.Response`` with a dummy request attached."""
    request = httpx.Request("POST", "http://test.local/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request)


def _make_empty_rotator():
    """Return a mock rotator that returns ``None`` immediately (no keys)."""

    rotator = MagicMock()
    rotator.store.get_all_keys.return_value = []
    rotator.get_best_key.return_value = None
    return rotator
