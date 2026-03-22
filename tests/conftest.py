"""Shared test fixtures for the PNW Campsites test suite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.monitor.db import WatchDB
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    BookingSystem,
    Campground,
    CampgroundAvailability,
    CampsiteAvailability,
)

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
