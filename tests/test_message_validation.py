"""Tests for message normalization in chat.py _normalize_messages."""

from __future__ import annotations

from llm_apipool.api.routes.chat import _normalize_messages


class TestNormalizeMessages:
    """_normalize_messages tolerates common client payload quirks."""

    def test_function_role_mapped_to_tool(self) -> None:
        messages = [{"role": "function", "name": "get_weather", "content": "sunny"}]
        _normalize_messages(messages)
        assert messages[0]["role"] == "tool"

    def test_developer_role_mapped_to_system(self) -> None:
        messages = [{"role": "developer", "content": "be helpful"}]
        _normalize_messages(messages)
        assert messages[0]["role"] == "system"

    def test_assistant_null_content_with_tool_calls_preserved(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "function": {"name": "f"}}],
            }
        ]
        _normalize_messages(messages)
        # content stays None because tool_calls is present
        assert messages[0]["content"] is None

    def test_assistant_null_content_without_tool_calls_filled(self) -> None:
        messages = [{"role": "assistant", "content": None}]
        _normalize_messages(messages)
        assert messages[0]["content"] == ""

    def test_tool_null_content_filled(self) -> None:
        messages = [{"role": "tool", "content": None, "tool_call_id": "call_1"}]
        _normalize_messages(messages)
        assert messages[0]["content"] == ""

    def test_normal_messages_unchanged(self) -> None:
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        _normalize_messages(messages)
        assert messages[0]["content"] == "hello"
        assert messages[1]["content"] == "hi there"

    def test_empty_messages(self) -> None:
        messages: list[dict] = []
        _normalize_messages(messages)
        assert messages == []
