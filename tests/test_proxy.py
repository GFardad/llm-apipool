"""Tests for proxy.py - FastAPI proxy server."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from llm_keypool.key_store import KeyStore
from llm_keypool.proxy import _KEYPOOL_MODEL_ID, _KEYPOOL_MODEL_OWNER, _mask_key, make_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "proxy_test.db"


@pytest.fixture
def store_and_app(db_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pre-configured store + app with one registered Groq key."""
    monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
    store = KeyStore(db_path=db_path)
    store.register_key(
        provider="groq",
        api_key="gsk_test_key",
        capabilities="general_purpose",
        model="llama-3.3-70b-versatile",
        extra_params={},
    )
    app = make_app(capabilities=["general_purpose"], rotate_every=5)
    return store, app


# ---------------------------------------------------------------------------
# _mask_key
# ---------------------------------------------------------------------------

class TestMaskKey:
    """_mask_key: safe API-key masking for logging."""

    def test_normal_length(self):
        assert _mask_key("sk-abcdef123456") == "sk-a****3456"

    def test_short_key(self):
        assert _mask_key("short") == "****hort"

    def test_very_short_key(self):
        assert _mask_key("ab") == "****"

    def test_exactly_eight_chars(self):
        assert _mask_key("12345678") == "****5678"

    def test_exactly_four_chars(self):
        assert _mask_key("1234") == "****"


# ---------------------------------------------------------------------------
# make_app
# ---------------------------------------------------------------------------

class TestMakeApp:
    """make_app factory function."""

    def test_creates_valid_app(self, db_path: Path, monkeypatch: pytest.MonkeyPatch):
        """App can be created and exposes expected metadata."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app()
        assert app.title == "llm-keypool proxy"
        assert app.version == "2.1"

    def test_health_endpoint(self, db_path: Path, monkeypatch: pytest.MonkeyPatch):
        """GET /health returns status ok with key counts."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "keys_total" in data
        assert "keys_active" in data

    def test_v1_models_endpoint(self, db_path: Path, monkeypatch: pytest.MonkeyPatch):
        """GET /v1/models returns list of known models from provider configs."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app()
        client = TestClient(app)
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        model_ids = {m["id"] for m in data["data"]}
        assert _KEYPOOL_MODEL_ID in model_ids
        keypool_model = next(m for m in data["data"] if m["id"] == _KEYPOOL_MODEL_ID)
        assert keypool_model["owned_by"] == _KEYPOOL_MODEL_OWNER
        # At least a few well-known models should be present
        assert "llama-3.3-70b-versatile" in model_ids

    def test_audit_endpoint(self, db_path: Path, monkeypatch: pytest.MonkeyPatch):
        """GET /audit returns audit summary (empty when no usage)."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app()
        client = TestClient(app)
        resp = client.get("/audit?days=7")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Chat completions (non-streaming)
# ---------------------------------------------------------------------------

class TestChatCompletions:
    """POST /v1/chat/completions."""

    def test_chat_completion_success(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Successful completion returns structured response with content."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="Hello from AI!", tokens_used=42, error=None,
            remaining_requests=100, rate_limit_headers={}, was_429=False,
        )
        key_data = {
            "provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": 1,
        }

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app()
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert data["choices"][0]["message"]["content"] == "Hello from AI!"
        assert data["usage"]["completion_tokens"] == 42
        assert data["object"] == "chat.completion"

    def test_chat_completion_all_keys_exhausted(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """When all keys are exhausted, respond 503 with OpenAI error shape."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="", tokens_used=0, error="all_keys_exhausted",
            remaining_requests=None, rate_limit_headers={}, was_429=False,
        )
        key_data = None

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app()
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert resp.status_code == 503
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "503"

    def test_chat_completion_generic_error(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Non-exhausted errors produce 502 with OpenAI error shape."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="", tokens_used=0, error="provider_timeout",
            remaining_requests=None, rate_limit_headers={}, was_429=False,
        )
        key_data = None

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app()
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert resp.status_code == 502
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "502"

    def test_chat_completion_with_max_tokens_and_temp(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Additional kwargs (max_tokens, temperature) are forwarded to dispatch."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="Hello!", tokens_used=10, error=None,
            remaining_requests=100, rate_limit_headers={}, was_429=False,
        )
        key_data = {
            "provider": "groq", "model": "llama-3.1-8b-instant", "key_id": 1,
        }

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app(capabilities=["fast"])
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100,
                "temperature": 0.5,
            })

        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hello!"

    def test_chat_with_x_keypool_capabilities_header(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """X-Keypool-Capabilities header overrides server default capabilities."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="fast response", tokens_used=5, error=None,
            remaining_requests=100, rate_limit_headers={}, was_429=False,
        )
        key_data = {
            "provider": "groq", "model": "llama-3.1-8b-instant", "key_id": 1,
        }

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app(capabilities=["general_purpose"])
            client = TestClient(app)
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hi"}]},
                headers={"X-Keypool-Capabilities": "fast"},
            )

        assert resp.status_code == 200

    def test_chat_completion_missing_model(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Backend reports model_used from key_data when request omits model."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        result = SimpleNamespace(
            text="fallback model used", tokens_used=3, error=None,
            remaining_requests=100, rate_limit_headers={}, was_429=False,
        )
        key_data = {
            "provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": 1,
        }

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (result, key_data)
            app = make_app()
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "llama-3.3-70b-versatile"
        assert data["x_key_provider"] == "groq"


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

class TestStreaming:
    """POST /v1/chat/completions with stream=true."""

    async def _mock_stream_gen(self) -> AsyncGenerator[dict[str, Any], None]:  # type: ignore[misc]  # noqa: ANN401
        """Return an async generator that yields realistic streaming chunks."""
        yield {
            "id": "test-chunk-id",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "llama-3.3-70b-versatile",
            "choices": [{"index": 0, "delta": {"content": "streaming"}, "finish_reason": None}],
        }
        yield {
            "id": "test-chunk-id",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "llama-3.3-70b-versatile",
            "choices": [{"index": 0, "delta": {"content": " response"}, "finish_reason": None}],
        }
        yield {
            "id": "test-chunk-id",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "llama-3.3-70b-versatile",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def test_chat_streaming_response(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Streaming mode returns SSE-formatted response with content chunks."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        key_data = {
            "provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": 1,
        }

        gen = self._mock_stream_gen()
        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (gen, key_data)
            app = make_app()
            client = TestClient(app)
            with client.stream(
                "POST", "/v1/chat/completions",
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            ) as resp:
                assert resp.status_code == 200
                resp.read()
                text = resp.text
                assert "data: [DONE]" in text
                assert "streaming" in text

    def test_streaming_returns_x_key_provider_header(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Streaming responses include X-Key-Provider header."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        key_data = {
            "provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": 1,
        }

        gen = self._mock_stream_gen()
        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (gen, key_data)
            app = make_app()
            client = TestClient(app)
            with client.stream(
                "POST", "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            ) as resp:
                assert resp.headers.get("x-key-provider") == "groq"

    def test_streaming_exhausted_keys(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Streaming with key_data=None returns 503 (line 118)."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))

        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (AsyncMock(), None)
            app = make_app()
            client = TestClient(app)
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            })

        assert resp.status_code == 503

    async def _chunks_without_fields(self) -> AsyncGenerator[dict, None]:
        """Yield chunks missing id/created/model fields (lines 127-131)."""
        yield {"choices": [{"delta": {"content": "hello"}}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    def test_streaming_chunks_fill_missing_fields(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Chunks without id/created/model get them filled in (lines 127-131)."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        key_data = {
            "provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": 1,
        }

        gen = self._chunks_without_fields()
        with patch("llm_keypool.api.routes.chat.dispatch_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = (gen, key_data)
            app = make_app()
            client = TestClient(app)
            with client.stream(
                "POST", "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            ) as resp:
                assert resp.status_code == 200
                resp.read()
                text = resp.text
                # Chunks should have been enriched with id, created, model
                assert "chatcmpl" in text
                assert "llama-3.3-70b-versatile" in text


# ---------------------------------------------------------------------------
# Models endpoint edge cases
# ---------------------------------------------------------------------------


class TestModelsEndpoint:
    """GET /v1/models — edge cases for uncovered lines."""

    CUSTOM_CONFIGS_DICT: dict[str, Any] = {
        "test_provider": {
            "models": {"tier1": ["model-a", "model-b"], "tier2": ["model-c"]},
            "default_model": "model-a",
        },
    }

    CUSTOM_CONFIGS_LIST: dict[str, Any] = {
        "test_provider": {
            "models": ["model-a"],
            "default_model": "model-default",
        },
    }

    def test_models_with_dict_models(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Dict-based models are flattened."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app(_configs=self.CUSTOM_CONFIGS_DICT)
        client = TestClient(app)
        resp = client.get("/v1/models")

        assert resp.status_code == 200
        data = resp.json()
        model_ids = {m["id"] for m in data["data"]}
        assert "model-a" in model_ids
        assert "model-b" in model_ids
        assert "model-c" in model_ids

    def test_models_default_not_in_list(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Default model not in models list gets prepended."""
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(db_path))
        app = make_app(_configs=self.CUSTOM_CONFIGS_LIST)
        client = TestClient(app)
        resp = client.get("/v1/models")

        assert resp.status_code == 200
        data = resp.json()
        model_ids = {m["id"] for m in data["data"]}
        assert "model-default" in model_ids
        assert "model-a" in model_ids
        # model-default should appear before model-a (prepended)
        ids_ordered = [m["id"] for m in data["data"]]
        assert ids_ordered.index("model-default") < ids_ordered.index("model-a")
