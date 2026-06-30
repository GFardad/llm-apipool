"""Tests for delta.content normalization in _stream_utils.py."""

from __future__ import annotations

from llm_apipool.providers._stream_utils import _normalize_delta_content


class TestNormalizeDeltaContent:
    """_normalize_delta_content converts various delta.content shapes to str | None."""

    def test_none_passthrough(self) -> None:
        assert _normalize_delta_content(None) is None

    def test_string_passthrough(self) -> None:
        assert _normalize_delta_content("hello") == "hello"

    def test_empty_string(self) -> None:
        assert _normalize_delta_content("") == ""

    def test_list_of_content_parts(self) -> None:
        content = [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "World"},
        ]
        assert _normalize_delta_content(content) == "Hello World"

    def test_list_with_mixed_types(self) -> None:
        content = [
            {"type": "text", "text": "Part1"},
            "literal_string",
        ]
        assert _normalize_delta_content(content) == "Part1literal_string"

    def test_list_with_empty_parts(self) -> None:
        content = [
            {"type": "text", "text": ""},
            {"type": "text", "text": "valid"},
        ]
        assert _normalize_delta_content(content) == "valid"

    def test_list_all_empty_returns_none(self) -> None:
        content = [
            {"type": "text", "text": ""},
            {"type": "text", "text": ""},
        ]
        assert _normalize_delta_content(content) is None

    def test_empty_list_returns_none(self) -> None:
        assert _normalize_delta_content([]) is None

    def test_uses_value_field_fallback(self) -> None:
        content = [{"value": "fallback_text"}]
        assert _normalize_delta_content(content) == "fallback_text"

    def test_non_str_non_list_converted_to_str(self) -> None:
        assert _normalize_delta_content(123) == "123"
        assert _normalize_delta_content(True) == "True"

    def test_list_with_missing_text_key(self) -> None:
        content = [{"type": "text"}]  # no text key
        assert _normalize_delta_content(content) is None
