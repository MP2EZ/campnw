"""Security-audit hardening (2026-11-22): SEC-08, SEC-09, SEC-10, SEC-13, SEC-15."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.routes import auth as auth_routes
from pnw_campsites.routes import sharing


class TestIngestBodyLimit:
    """SEC-08: the anonymous PostHog proxy must not buffer unbounded bodies."""

    @pytest.fixture
    def upstream(self, monkeypatch, api_client):
        client = MagicMock()
        client.request = AsyncMock(return_value=httpx.Response(200, content=b"ok"))
        monkeypatch.setattr(api_module, "_posthog_client", client)
        monkeypatch.setattr(api_module, "_INGEST_MAX_BODY", 1024)
        return client

    def test_small_body_forwarded(self, api_client: TestClient, upstream):
        resp = api_client.post("/ingest/e/", content=b"x" * 1024)
        assert resp.status_code == 200
        assert upstream.request.await_args.kwargs["content"] == b"x" * 1024

    def test_declared_oversize_rejected(self, api_client: TestClient, upstream):
        resp = api_client.post("/ingest/e/", content=b"x" * 1025)
        assert resp.status_code == 413
        upstream.request.assert_not_called()

    def test_chunked_oversize_rejected(self, api_client: TestClient, upstream):
        def chunks():
            for _ in range(5):
                yield b"x" * 300

        resp = api_client.post("/ingest/e/", content=chunks())
        assert resp.status_code == 413
        upstream.request.assert_not_called()


class TestDeleteSupabaseUser:
    """SEC-09: GoTrue admin needs the bearer token, and a failure must not be
    reported as a deleted account."""

    URL = "https://sb.example.co/auth/v1/admin/users/abc"

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://sb.example.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

    @respx.mock
    async def test_sends_bearer_and_apikey(self):
        route = respx.delete(self.URL).mock(return_value=httpx.Response(200))
        await auth_routes._delete_supabase_user("abc")
        headers = route.calls[0].request.headers
        assert headers["apikey"] == "service-key"
        assert headers["Authorization"] == "Bearer service-key"

    @respx.mock
    async def test_already_gone_is_success(self):
        respx.delete(self.URL).mock(return_value=httpx.Response(404))
        await auth_routes._delete_supabase_user("abc")

    @respx.mock
    async def test_failure_raises(self):
        respx.delete(self.URL).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await auth_routes._delete_supabase_user("abc")

    def test_route_keeps_account_when_supabase_fails(
        self, api_client: TestClient, monkeypatch,
    ):
        from tests.test_api_auth import _auth_headers, _make_jwt

        headers = _auth_headers(_make_jwt(supabase_id="abc"))
        user_id = api_client.get("/api/auth/me", headers=headers).json()["user"]["id"]
        monkeypatch.setattr(
            auth_routes, "_delete_supabase_user",
            AsyncMock(side_effect=httpx.ConnectError("down")),
        )

        resp = api_client.delete("/api/auth/me", headers=headers)

        assert resp.status_code == 502
        assert api_module._watch_db.get_user_by_id(user_id) is not None


def test_facility_id_with_trailing_newline_rejected(api_client: TestClient):
    """SEC-10: `$` matches before a trailing newline; fullmatch doesn't."""
    resp = api_client.get(
        "/api/check/232465%0A",
        params={"start_date": "2027-06-01", "end_date": "2027-06-03"},
    )
    assert resp.status_code == 400


class TestStaticFile:
    """SEC-13: containment is a path check, not a string-prefix check."""

    def test_serves_file_inside(self, tmp_path):
        static = tmp_path / "static"
        (static / "assets").mkdir(parents=True)
        (static / "assets" / "app.js").write_text("x")
        assert api_module._static_file(static, "assets/app.js") == (
            static / "assets" / "app.js"
        ).resolve()

    def test_sibling_with_shared_prefix_not_served(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (tmp_path / "static-old").mkdir()
        (tmp_path / "static-old" / "secret.txt").write_text("s")
        assert api_module._static_file(static, "../static-old/secret.txt") is None

    def test_missing_file_not_served(self, tmp_path):
        assert api_module._static_file(tmp_path, "nope.js") is None


class TestShareViewLimiter:
    """SEC-15: attacker-chosen UUIDs must not grow the limiter's dict."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        sharing._share_view_counts.clear()

    def test_malformed_uuid_404_without_touching_limiter(self, api_client: TestClient):
        resp = api_client.get("/api/shared/" + "a" * 500)
        assert resp.status_code == 404
        assert sharing._share_view_counts == {}

    def test_ip_limited_requests_add_no_uuid_keys(self):
        for i in range(30):
            assert sharing._check_share_rate_limit(f"{i:032x}", "1.2.3.4")
        size = len(sharing._share_view_counts)
        assert not sharing._check_share_rate_limit("f" * 32, "1.2.3.4")
        assert len(sharing._share_view_counts) == size
