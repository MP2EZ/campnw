"""Tests for the global FastAPI exception handler that forwards errors to PostHog.

The handler uses asyncio.create_task + to_thread + wait_for so the SDK call
can never block the response. These tests lock in:
- HTTPException is NOT captured (intentional 4xx/5xx, not bugs)
- Plain unhandled exceptions ARE captured with request context
- The handler returns 500 even when get_posthog_client() returns None
- The handler returns 500 quickly even when the SDK hangs (the design lesson
  from the 2026-04-30 /ingest proxy 502 incident)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module


@pytest.fixture
def app_with_raising_routes(api_client: TestClient):
    """Adds two routes that raise on demand; cleans them up after the test."""

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


def _wait_for_capture(mock_client: MagicMock, timeout_s: float = 2.0) -> None:
    """Wait until the background asyncio task has called capture_exception."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if mock_client.capture_exception.called:
            return
        time.sleep(0.02)


def test_runtime_error_is_captured_with_request_context(
    app_with_raising_routes: TestClient,
):
    mock_client = MagicMock()
    with patch("pnw_campsites.api.get_posthog_client", return_value=mock_client):
        client = TestClient(api_module.app, raise_server_exceptions=False)
        response = client.get("/_test_raises_runtime")
        # capture runs as an asyncio.create_task — give the loop a moment
        _wait_for_capture(mock_client)

    assert response.status_code == 500
    mock_client.capture_exception.assert_called_once()
    args, kwargs = mock_client.capture_exception.call_args
    assert isinstance(args[0], RuntimeError)
    assert str(args[0]) == "boom"
    assert kwargs["properties"]["path"] == "/_test_raises_runtime"
    assert kwargs["properties"]["method"] == "GET"
    assert "$current_url" in kwargs["properties"]


def test_http_exception_is_not_captured(app_with_raising_routes: TestClient):
    """HTTPException is intentional 4xx/5xx; FastAPI's built-in handler runs
    first via MRO dispatch. Without this guarantee, the error dashboard would
    fill with noise from every 404."""
    mock_client = MagicMock()
    with patch("pnw_campsites.api.get_posthog_client", return_value=mock_client):
        response = app_with_raising_routes.get("/_test_raises_http_404")
        # Even if a stray task were scheduled, give it a beat to run
        time.sleep(0.05)

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


def test_handler_uses_create_task_for_isolation(app_with_raising_routes: TestClient):
    """The defining lesson from the 2026-04-30 /ingest proxy 502 incident:
    PostHog SDK calls must run as fire-and-forget asyncio tasks, never
    awaited from the response path. We verify the handler dispatches via
    asyncio.create_task — if a future refactor accidentally `awaits` the
    capture, this test fails.

    (We test structure rather than timing because Starlette's TestClient
    drains pending asyncio tasks before returning, masking the prod-relevant
    behavior. In real uvicorn, create_task returns immediately without
    blocking the response.)
    """
    scheduled = []
    real_create_task = asyncio.create_task

    def fake_create_task(coro, *args, **kwargs):
        scheduled.append(coro)
        coro.close()  # avoid an un-awaited-coroutine warning
        return MagicMock()

    with patch("pnw_campsites.api.asyncio.create_task", side_effect=fake_create_task):
        client = TestClient(api_module.app, raise_server_exceptions=False)
        response = client.get("/_test_raises_runtime")

    assert response.status_code == 500
    assert len(scheduled) == 1, (
        "Handler must dispatch capture via asyncio.create_task. "
        "Direct await or sync call would re-introduce the prod 502 risk."
    )
    # Sanity: the scheduled object is a coroutine (the redesign's hallmark)
    assert asyncio.iscoroutine(scheduled[0]) or hasattr(scheduled[0], "__await__")
    _ = real_create_task  # silence unused


def test_handler_swallows_sdk_errors(app_with_raising_routes: TestClient):
    """If the SDK itself raises (deprecation error, version mismatch, network
    failure inside the SDK), the response must still be 500. Observability
    bugs cannot cascade into the response path."""
    failing_client = MagicMock()
    failing_client.capture_exception.side_effect = RuntimeError("SDK is broken")

    with patch("pnw_campsites.api.get_posthog_client", return_value=failing_client):
        client = TestClient(api_module.app, raise_server_exceptions=False)
        response = client.get("/_test_raises_runtime")

    assert response.status_code == 500
