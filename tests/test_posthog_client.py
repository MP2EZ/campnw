"""Tests for the PostHog client singleton."""

from unittest.mock import MagicMock, patch

import pytest

import pnw_campsites.posthog_client as phmod


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the module-level singleton before each test."""
    phmod._client = None
    yield
    phmod._client = None


@patch.dict("os.environ", {}, clear=True)
@patch("pnw_campsites.posthog_client.Posthog")
def test_returns_none_when_no_env_vars(mock_posthog):
    result = phmod.get_posthog_client()
    assert result is None
    mock_posthog.assert_not_called()


@patch.dict("os.environ", {"POSTHOG_PROJECT_TOKEN": "phc_test123"}, clear=True)
@patch("pnw_campsites.posthog_client.Posthog")
def test_returns_client_when_posthog_token_set(mock_posthog):
    mock_posthog.return_value = MagicMock()
    result = phmod.get_posthog_client()
    assert result is not None
    mock_posthog.assert_called_once_with(
        "phc_test123",
        host="https://eu.i.posthog.com",
        enable_exception_autocapture=True,
    )


@patch.dict("os.environ", {"VITE_PUBLIC_POSTHOG_PROJECT_TOKEN": "phc_vite456"}, clear=True)
@patch("pnw_campsites.posthog_client.Posthog")
def test_falls_back_to_vite_token(mock_posthog):
    mock_posthog.return_value = MagicMock()
    result = phmod.get_posthog_client()
    assert result is not None
    mock_posthog.assert_called_once_with(
        "phc_vite456",
        host="https://eu.i.posthog.com",
        enable_exception_autocapture=True,
    )


@patch.dict("os.environ", {"POSTHOG_PROJECT_TOKEN": "phc_test123"}, clear=True)
@patch("pnw_campsites.posthog_client.Posthog")
def test_returns_same_instance_on_repeated_calls(mock_posthog):
    sentinel = MagicMock()
    mock_posthog.return_value = sentinel
    first = phmod.get_posthog_client()
    second = phmod.get_posthog_client()
    assert first is second
    mock_posthog.assert_called_once()
