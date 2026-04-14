"""Shared test fixtures for the PNW Campsites test suite."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
import pnw_campsites.auth as auth_module
from pnw_campsites.monitor.db import WatchDB
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    BookingSystem,
    Campground,
    CampgroundAvailability,
    CampsiteAvailability,
)

# ---------------------------------------------------------------------------
# Supabase JWT test helpers
# ---------------------------------------------------------------------------

FAKE_SUPABASE_JWT_SECRET = "test-supabase-jwt-secret-that-is-at-least-32-characters"


def make_supabase_jwt(
    supabase_id: str | None = None,
    email: str = "test@example.com",
    expired: bool = False,
    role: str = "authenticated",
    aud: str = "authenticated",
) -> str:
    """Create a test JWT mimicking Supabase format."""
    sub = supabase_id or str(uuid.uuid4())
    exp = datetime.now(UTC) + (timedelta(days=-1) if expired else timedelta(hours=1))
    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "aud": aud,
        "exp": exp,
        "iat": datetime.now(UTC),
    }
    return pyjwt.encode(payload, FAKE_SUPABASE_JWT_SECRET, algorithm="HS256")


def auth_headers(token: str) -> dict[str, str]:
    """Return Authorization header dict for a Bearer token."""
    return {"Authorization": f"Bearer {token}"}


def signup_and_auth(
    client,
    email: str = "test@example.com",
    display_name: str = "Test User",
) -> tuple[dict, dict[str, str]]:
    """Create a user via Supabase JWT auto-provisioning and return (user_dict, headers).

    This replaces the old pattern of POSTing to /api/auth/signup in tests.
    """
    token = make_supabase_jwt(email=email)
    headers = auth_headers(token)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    user_data = resp.json()["user"]
    if display_name:
        resp2 = client.patch(
            "/api/auth/me",
            json={"display_name": display_name},
            headers=headers,
        )
        user_data = resp2.json()["user"]
    return user_data, headers

# -------------------------------------------------------------------
# Database fixtures
# -------------------------------------------------------------------


@pytest.fixture
def watch_db(tmp_path: Path) -> WatchDB:
    """Isolated WatchDB backed by a temp SQLite file."""
    db = WatchDB(tmp_path / "watches.db")
    yield db
    db.close()


@pytest.fixture
def registry(tmp_path: Path) -> CampgroundRegistry:
    """Isolated CampgroundRegistry backed by a temp SQLite file."""
    reg = CampgroundRegistry(tmp_path / "registry.db")
    yield reg
    reg.close()


# -------------------------------------------------------------------
# API test client
# -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_jwks_client():
    """Mock the JWKS client so tests validate JWTs with the test HS256 secret."""
    from unittest.mock import MagicMock

    # Mock signing key: .key returns the raw secret for HS256 verification
    mock_signing_key = MagicMock()
    mock_signing_key.key = FAKE_SUPABASE_JWT_SECRET

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

    auth_module._jwks_client = mock_client
    yield
    auth_module._jwks_client = None


@pytest.fixture
def api_client(tmp_path: Path) -> TestClient:
    """FastAPI TestClient with patched DB and registry."""
    original_connect = sqlite3.connect

    def patched_connect(path, *args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return original_connect(path, *args, **kwargs)

    with patch("sqlite3.connect", patched_connect):
        db = WatchDB(tmp_path / "watches.db")
        api_module._watch_db = db
        registry_mock = MagicMock()
        registry_mock.get_by_facility_id.return_value = None
        registry_mock.search.return_value = []
        api_module._registry = registry_mock
        api_module._engine = MagicMock()

        client = TestClient(
            api_module.app,
            raise_server_exceptions=True,
            base_url="https://testserver",
        )
        yield client
        db.close()


# -------------------------------------------------------------------
# Data factories
# -------------------------------------------------------------------


def make_campground(**overrides) -> Campground:
    """Create a Campground with sensible defaults, override any field."""
    defaults = {
        "facility_id": "232465",
        "name": "Test Campground",
        "booking_system": BookingSystem.RECGOV,
        "latitude": 46.75,
        "longitude": -121.80,
        "state": "WA",
        "region": "Mt. Rainier NP",
        "tags": ["lakeside"],
        "enabled": True,
    }
    defaults.update(overrides)
    return Campground(**defaults)


def make_campsite_availability(
    campsite_id: str = "123456",
    site: str = "A001",
    loop: str = "Loop A",
    campsite_type: str = "STANDARD NONELECTRIC",
    max_people: int = 6,
    dates_status: dict[str, str] | None = None,
) -> CampsiteAvailability:
    """Create a CampsiteAvailability with specified date→status mapping."""
    if dates_status is None:
        dates_status = {
            "2026-06-01T00:00:00.000Z": "Available",
            "2026-06-02T00:00:00.000Z": "Available",
            "2026-06-03T00:00:00.000Z": "Reserved",
        }
    return CampsiteAvailability(
        campsite_id=campsite_id,
        site=site,
        loop=loop,
        campsite_type=campsite_type,
        type_of_use="Overnight",
        min_num_people=0,
        max_num_people=max_people,
        availabilities={
            k: AvailabilityStatus(v) for k, v in dates_status.items()
        },
    )


def make_campground_availability(
    facility_id: str = "232465",
    campsites: dict[str, CampsiteAvailability] | None = None,
) -> CampgroundAvailability:
    """Create a CampgroundAvailability wrapping multiple campsites."""
    if campsites is None:
        site = make_campsite_availability()
        campsites = {site.campsite_id: site}
    return CampgroundAvailability(
        facility_id=facility_id,
        campsites=campsites,
    )
