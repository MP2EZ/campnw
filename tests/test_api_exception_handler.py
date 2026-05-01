"""Tests for the global FastAPI exception handler that forwards errors to PostHog."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module


@pytest.fixture
def app_with_raising_routes(api_client: TestClient):
    """Adds two routes that raise on demand, cleans them up after the test."""

    @api_module.app.get("/_test_raises_runtime")
    async def _raise_runtime():
        raise RuntimeError("boom")

    @api_module.app.get("/_test_raises_http_404")
    async def _raise_http_404():
        raise HTTPException(status_code=404, detail="not found")

    yield api_client

    api_module.app.routes[:] = [
        r for r in api_module.app.routes
        if not (hasattr(r, "path") and str(r.path).startswith("/_test_"))
    ]


def test_runtime_error_is_captured_with_request_context(app_with_raising_routes: TestClient):
    mock_client = MagicMock()
    with patch("pnw_campsites.api.get_posthog_client", return_value=mock_client):
        # api_client uses raise_server_exceptions=True, which would re-raise
        # before we can observe the 500 response. Use a permissive client here.
        client = TestClient(api_module.app, raise_server_exceptions=False)
        response = client.get("/_test_raises_runtime")

    assert response.status_code == 500

    mock_client.capture_exception.assert_called_once()
    args, kwargs = mock_client.capture_exception.call_args
    assert isinstance(args[0], RuntimeError)
    assert str(args[0]) == "boom"
    assert kwargs["properties"]["path"] == "/_test_raises_runtime"
    assert kwargs["properties"]["method"] == "GET"
    assert "$current_url" in kwargs["properties"]


def test_http_exception_is_not_captured(app_with_raising_routes: TestClient):
    """HTTPException is intentional 4xx/5xx; FastAPI's built-in handler runs first
    via MRO dispatch, so our Exception handler never fires for these. Without this
    guarantee, the error dashboard would fill with noise from every 404."""
    mock_client = MagicMock()
    with patch("pnw_campsites.api.get_posthog_client", return_value=mock_client):
        response = app_with_raising_routes.get("/_test_raises_http_404")

    assert response.status_code == 404
    mock_client.capture_exception.assert_not_called()


def test_handler_does_not_crash_when_client_unconfigured(
    app_with_raising_routes: TestClient,
):
    """If POSTHOG_PROJECT_TOKEN is unset, get_posthog_client() returns None.
    The handler must still return 500 instead of raising AttributeError."""
    with patch("pnw_campsites.api.get_posthog_client", return_value=None):
        client = TestClient(api_module.app, raise_server_exceptions=False)
        response = client.get("/_test_raises_runtime")

    assert response.status_code == 500
