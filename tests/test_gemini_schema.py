"""Tests for Gemini vendor extension stripping in openai_compat.py."""

from __future__ import annotations

from llm_apipool.providers.openai_compat import (
    _strip_vendor_extensions,
    _sanitize_tools_for_provider,
)


class TestStripVendorExtensions:
    """_strip_vendor_extensions removes x-* keys from JSON Schema dicts."""

    def test_strips_x_google_enum_descriptions(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "font": {
                    "type": "string",
                    "enum": ["INTER", "LEXEND"],
                    "x-google-enum-descriptions": ["Inter.", "Lexend."],
                }
            },
        }
        cleaned = _strip_vendor_extensions(schema)
        props = cleaned["properties"]["font"]
        assert "x-google-enum-descriptions" not in props
        assert props["type"] == "string"
        assert props["enum"] == ["INTER", "LEXEND"]

    def test_preserves_real_property_names(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "x-user-id": {"type": "string"},
                "normal_prop": {"type": "integer"},
            },
        }
        cleaned = _strip_vendor_extensions(schema)
        # "x-user-id" is a property VALUE name, not a schema KEY — preserve it
        assert "x-user-id" in cleaned["properties"]
        assert "normal_prop" in cleaned["properties"]

    def test_strips_x_prefix_at_multiple_levels(self) -> None:
        schema = {
            "type": "object",
            "x-internal": "should be removed",
            "properties": {
                "name": {
                    "type": "string",
                    "x-extra": "removed",
                    "x-test": "removed",
                }
            },
            "definitions": {
                "Address": {
                    "type": "object",
                    "x-deprecated": True,
                }
            },
        }
        cleaned = _strip_vendor_extensions(schema)
        assert "x-internal" not in cleaned
        assert "x-extra" not in cleaned["properties"]["name"]
        assert "x-test" not in cleaned["properties"]["name"]
        assert "x-deprecated" not in cleaned["definitions"]["Address"]

    def test_handles_nested_arrays(self) -> None:
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "x-vendor-key": "remove",
                "properties": {"val": {"type": "string"}},
            },
        }
        cleaned = _strip_vendor_extensions(schema)
        assert "x-vendor-key" not in cleaned["items"]

    def test_non_dict_passthrough(self) -> None:
        assert _strip_vendor_extensions("string") == "string"  # type: ignore[arg-type]
        assert _strip_vendor_extensions(42) == 42  # type: ignore[arg-type]
        assert _strip_vendor_extensions(None) is None  # type: ignore[arg-type]

    def test_empty_dict(self) -> None:
        assert _strip_vendor_extensions({}) == {}

    def test_strips_x_underscore_prefix(self) -> None:
        schema = {"type": "object", "x_extra_param": "remove", "x_another": "remove"}
        cleaned = _strip_vendor_extensions(schema)
        assert "x_extra_param" not in cleaned
        assert "x_another" not in cleaned


class TestSanitizeToolsForProvider:
    """_sanitize_tools_for_provider applies per-provider sanitization."""

    def test_google_strips_extensions(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_func",
                    "parameters": {
                        "type": "object",
                        "x-vendor": "remove",
                        "properties": {"arg": {"type": "string", "x-extra": "remove"}},
                    },
                },
            }
        ]
        sanitized = _sanitize_tools_for_provider(tools, "google")
        params = sanitized[0]["function"]["parameters"]
        assert "x-vendor" not in params
        assert "x-extra" not in params["properties"]["arg"]

    def test_non_google_passthrough(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_func",
                    "parameters": {"type": "object", "x-vendor": "keep"},
                },
            }
        ]
        sanitized = _sanitize_tools_for_provider(tools, "groq")
        assert sanitized == tools

    def test_empty_tools(self) -> None:
        assert _sanitize_tools_for_provider([], "google") == []

    def test_no_function_key(self) -> None:
        tools = [{"type": "function"}]  # no function key
        sanitized = _sanitize_tools_for_provider(tools, "google")
        assert sanitized == tools
