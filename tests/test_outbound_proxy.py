"""Tests for outbound proxy support in connection_pool.py."""

from __future__ import annotations

import os
from unittest.mock import patch

from llm_apipool.core.connection_pool import (
    _resolve_proxy_url,
    _get_proxy_bypass_set,
    _should_bypass_proxy,
)


class TestResolveProxyUrl:
    """_resolve_proxy_url reads proxy URL from environment."""

    def test_returns_none_when_not_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert _resolve_proxy_url() is None

    def test_reads_all_proxy_first(self) -> None:
        with patch.dict(os.environ, {"ALL_PROXY": "http://all:8080"}, clear=True):
            assert _resolve_proxy_url() == "http://all:8080"

    def test_https_proxy_fallback(self) -> None:
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://https:8080"}, clear=True):
            assert _resolve_proxy_url() == "http://https:8080"

    def test_http_proxy_fallback(self) -> None:
        with patch.dict(os.environ, {"HTTP_PROXY": "http://http:8080"}, clear=True):
            assert _resolve_proxy_url() == "http://http:8080"

    def test_priority_order_all_overrides_https(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ALL_PROXY": "http://all:8080",
                "HTTPS_PROXY": "http://https:8080",
                "HTTP_PROXY": "http://http:8080",
            },
            clear=True,
        ):
            assert _resolve_proxy_url() == "http://all:8080"

    def test_lowercase_variants(self) -> None:
        with patch.dict(os.environ, {"all_proxy": "http://lower:8080"}, clear=True):
            assert _resolve_proxy_url() == "http://lower:8080"

    def test_ignores_empty_values(self) -> None:
        with patch.dict(
            os.environ,
            {"HTTP_PROXY": "", "HTTPS_PROXY": "  ", "ALL_PROXY": ""},
            clear=True,
        ):
            assert _resolve_proxy_url() is None


class TestGetProxyBypassSet:
    """_get_proxy_bypass_set parses NO_PROXY / no_proxy."""

    def test_returns_empty_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert _get_proxy_bypass_set() == set()

    def test_parses_comma_separated(self) -> None:
        with patch.dict(
            os.environ, {"NO_PROXY": "localhost,127.0.0.1,.internal"}, clear=True
        ):
            result = _get_proxy_bypass_set()
            assert result == {"localhost", "127.0.0.1", ".internal"}

    def test_lowercases_hosts(self) -> None:
        with patch.dict(
            os.environ, {"NO_PROXY": "LOCALHOST,API.EXAMPLE.COM"}, clear=True
        ):
            result = _get_proxy_bypass_set()
            assert "localhost" in result
            assert "api.example.com" in result

    def test_ignores_whitespace(self) -> None:
        with patch.dict(
            os.environ, {"NO_PROXY": " localhost , 127.0.0.1 "}, clear=True
        ):
            result = _get_proxy_bypass_set()
            assert "localhost" in result
            assert "127.0.0.1" in result

    def test_ignores_empty_parts(self) -> None:
        with patch.dict(os.environ, {"NO_PROXY": "localhost,,,127.0.0.1"}, clear=True):
            result = _get_proxy_bypass_set()
            assert result == {"localhost", "127.0.0.1"}

    def test_reads_no_proxy_lowercase(self) -> None:
        with patch.dict(os.environ, {"no_proxy": ".example.com"}, clear=True):
            result = _get_proxy_bypass_set()
            assert ".example.com" in result


class TestShouldBypassProxy:
    """_should_bypass_proxy checks if a URL should bypass the proxy."""

    def test_bypasses_exact_match(self) -> None:
        bypass = {"localhost", "127.0.0.1"}
        assert _should_bypass_proxy("http://localhost:8080", bypass) is True

    def test_bypasses_suffix_match(self) -> None:
        bypass = {".internal"}
        assert _should_bypass_proxy("http://service.internal", bypass) is True

    def test_no_bypass_for_non_matching(self) -> None:
        bypass = {".internal"}
        assert _should_bypass_proxy("http://example.com", bypass) is False

    def test_empty_bypass_set(self) -> None:
        assert _should_bypass_proxy("http://example.com", set()) is False

    def test_case_insensitive_match(self) -> None:
        bypass = {"LOCALHOST"}
        assert _should_bypass_proxy("http://localhost:3000", bypass) is True
