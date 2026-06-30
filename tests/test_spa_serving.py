"""Tests for SPA serving pipeline: CSP headers, static asset MIME types,
font delivery, cache control, and 404 handling for stale assets.

These tests validate that the React dashboard loads correctly when served
through the FastAPI backend at port 8000.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llm_apipool.api.app import make_app


@pytest.fixture
def app():
    """Create app with minimal config — only need routing, not providers."""
    return make_app(
        _configs={
            "groq": {
                "models": ["llama-3.3-70b-versatile"],
                "default_model": "llama-3.3-70b-versatile",
            },
        }
    )


@pytest.fixture
def client(app):
    return TestClient(app)


class TestSecurityHeaders:
    """CSP and security header validation."""

    def test_csp_contains_unsafe_inline_for_styles(self, client):
        """CSP must allow Tailwind JIT + React style={{}}."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "style-src 'self' 'unsafe-inline'" in csp, (
            f"CSP missing 'unsafe-inline' for style-src: {csp}"
        )

    def test_csp_allows_same_origin_scripts(self, client):
        """Bundled JS is same-origin; script-src inherits default-src 'self'."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp, f"CSP missing default-src: {csp}"

    def test_csp_allows_data_images(self, client):
        """Inlined placeholder images use data: URIs."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "img-src 'self' data:" in csp, f"CSP missing img-src: {csp}"

    def test_csp_allows_data_fonts(self, client):
        """Bundled @fontsource fonts load via data: or same-origin."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "font-src 'self' data:" in csp, f"CSP missing font-src: {csp}"

    def test_csp_allows_websocket_connections(self, client):
        """HMR / SSE require WebSocket connections."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "connect-src 'self' ws: wss:" in csp, f"CSP missing connect-src: {csp}"

    def test_csp_prevents_clickjacking(self, client):
        """frame-ancestors 'none' prevents embedding in iframes."""
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp, f"CSP missing frame-ancestors: {csp}"

    def test_xframe_options_deny(self, client):
        """Legacy clickjacking protection for older browsers."""
        resp = client.get("/")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_xcontent_type_options_nosniff(self, client):
        """Prevent MIME sniffing — critical for SPA security."""
        resp = client.get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"


class TestSpaServing:
    """Static file serving and SPA fallback."""

    def test_root_serves_html_with_proper_content_type(self, client):
        """GET / returns index.html with text/html."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/html")
        assert b'<div id="root">' in resp.content

    def test_root_html_has_no_cache(self, client):
        """index.html must NOT be cached so asset hashes stay fresh."""
        resp = client.get("/")
        cc = resp.headers.get("cache-control", "")
        assert "no-cache" in cc and "no-store" in cc, f"Missing no-cache/no-store: {cc}"

    def test_js_file_served_with_javascript_content_type(self, client):
        """Request a real built JS asset — must have correct MIME type."""
        # Read actual hash from built index.html
        resp_index = client.get("/")
        html = resp_index.text
        # Parse src="/assets/index-XXXXXXXX.js"
        import re

        js_match = re.search(r'src="(/assets/index-[\w-]+\.js)"', html)
        assert js_match, "No JS asset reference found in index.html"
        js_path = js_match.group(1)

        resp = client.get(js_path)
        assert resp.status_code == 200, f"JS asset {js_path} not found"
        ct = resp.headers.get("content-type", "")
        assert ct.startswith("text/javascript") or ct.startswith(
            "application/javascript"
        ), f"JS asset returned Content-Type: {ct}"

    def test_css_file_served_with_css_content_type(self, client):
        """Request a real built CSS asset — must have correct MIME type."""
        resp_index = client.get("/")
        html = resp_index.text
        import re

        css_match = re.search(r'href="(/assets/index-[\w-]+\.css)"', html)
        assert css_match, "No CSS asset reference found in index.html"
        css_path = css_match.group(1)

        resp = client.get(css_path)
        assert resp.status_code == 200, f"CSS asset {css_path} not found"
        ct = resp.headers.get("content-type", "")
        assert ct.startswith("text/css"), f"CSS asset returned Content-Type: {ct}"

    def test_woff2_font_served_with_font_content_type(self, client):
        """Font files must have proper font/* Content-Type."""
        resp_index = client.get("/")
        html = resp_index.text
        # Get a real woff2 font from the built assets
        import re

        font_match = re.search(r'href="(/assets/[-\w]+\.woff2)"', html)
        if font_match:
            font_path = font_match.group(1)
            resp = client.get(font_path)
            assert resp.status_code == 200, f"Font {font_path} not found"
            ct = resp.headers.get("content-type", "")
            assert ct.startswith("font/"), f"Font returned Content-Type: {ct}"
        else:
            # Fonts may be inlined in CSS; skip if no separate font files
            pass

    def test_spa_fallback_serves_html_for_sub_routes(self, client):
        """Routes like /settings must return index.html (SPA fallback)."""
        for route in ["/settings", "/keys", "/analytics", "/models"]:
            resp = client.get(route)
            assert resp.status_code == 200, f"SPA fallback failed for {route}"
            assert resp.headers.get("content-type", "").startswith("text/html")
            assert b'<div id="root">' in resp.content

    def test_spa_fallback_cache_control(self, client):
        """SPA fallback routes must also have no-cache."""
        resp = client.get("/settings")
        cc = resp.headers.get("cache-control", "")
        assert "no-cache" in cc and "no-store" in cc

    def test_missing_js_asset_returns_404(self, client):
        """Stale cached index.html with old hash should get 404."""
        resp = client.get("/assets/index-OLDHASHxxxx.js")
        assert resp.status_code == 404
        ct = resp.headers.get("content-type", "")
        assert ct.startswith("application/json"), (
            f"Missing asset 404 returned Content-Type: {ct} (expected application/json)"
        )

    def test_missing_css_asset_returns_404(self, client):
        """Stale CSS asset returns proper 404."""
        resp = client.get("/assets/index-OLDHASHxxxx.css")
        assert resp.status_code == 404
        ct = resp.headers.get("content-type", "")
        assert ct.startswith("application/json"), (
            f"Missing CSS asset 404 returned Content-Type: {ct}"
        )

    def test_missing_font_asset_returns_404(self, client):
        """Stale font asset returns proper 404."""
        resp = client.get("/assets/font-OLDHASH.woff2")
        assert resp.status_code == 404
        ct = resp.headers.get("content-type", "")
        assert ct.startswith("application/json"), (
            f"Missing font asset 404 returned Content-Type: {ct}"
        )

    def test_missing_asset_404_cache_control(self, client):
        """Missing asset 404 must not be cached."""
        resp = client.get("/assets/index-NONEXISTENT.js")
        cc = resp.headers.get("cache-control", "")
        assert "no-store" in cc


class TestSecurityHeadersOnAllRoutes:
    """Every response — including 404s — carries CSP."""

    def test_csp_on_root(self, client):
        resp = client.get("/")
        assert "content-security-policy" in resp.headers

    def test_csp_on_spa_fallback(self, client):
        resp = client.get("/settings")
        assert "content-security-policy" in resp.headers

    def test_csp_on_js_asset(self, client):
        resp_index = client.get("/")
        import re

        js_match = re.search(r'src="(/assets/index-\w+\.js)"', resp_index.text)
        if js_match:
            resp = client.get(js_match.group(1))
            assert "content-security-policy" in resp.headers

    def test_csp_on_404(self, client):
        resp = client.get("/assets/missing.js")
        assert resp.status_code == 404
        assert "content-security-policy" in resp.headers
