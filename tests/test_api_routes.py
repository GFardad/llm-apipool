from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from llm_keypool.api.app import make_app


@pytest.fixture
def app():
    return make_app(_configs={
        "groq": {"models": ["llama-3.3-70b-versatile"], "default_model": "llama-3.3-70b-versatile"},
    })


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def authenticated_client(app):
    """Client with admin user logged in."""
    client = TestClient(app)
    # Create admin user (first user) and get session cookie
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "testpass123"})
    # Extract session cookie from response
    cookies = resp.cookies
    return client


def test_root_endpoint(client):
    """Root serves the SPA (index.html) by default."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in resp.text


def test_settings_routing_strategy(authenticated_client):
    resp = authenticated_client.get("/api/settings/routing-strategy")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategy" in data


def test_settings_sticky(authenticated_client):
    resp = authenticated_client.get("/api/settings/sticky")
    assert resp.status_code == 200
    data = resp.json()
    assert "sticky_enabled" in data


def test_settings_handoff(authenticated_client):
    resp = authenticated_client.get("/api/settings/handoff")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data


def test_analytics_overview(authenticated_client):
    resp = authenticated_client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_keys" in data
    assert "active_keys" in data


def test_analytics_providers(authenticated_client):
    resp = authenticated_client.get("/api/analytics/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "penalties" in data


def test_models_list(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "LLM-Keypool" in {m["id"] for m in data["data"]}


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_audit_endpoint(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_list_providers(authenticated_client):
    resp = authenticated_client.get("/api/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
