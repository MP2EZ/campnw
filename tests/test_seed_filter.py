"""Tests for the seed_registry.py is_campground() filter logic."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from seed_registry import is_campground

from pnw_campsites.registry.models import RIDBFacility


def _facility(name: str, lat: float = 47.0, lon: float = -121.0, enabled: bool = True) -> RIDBFacility:
    """Create an RIDBFacility with given name and sensible PNW defaults."""
    return RIDBFacility(
        FacilityID="999",
        FacilityName=name,
        FacilityLatitude=lat,
        FacilityLongitude=lon,
        Enabled=enabled,
    )


class TestPositiveSignalBypass:
    """Names with 'campground' or 'camp' bypass the exclusion filter."""

    def test_campground_area_passes(self):
        """'Bumping Lake Campground Area' was previously excluded by \\barea\\b."""
        assert is_campground(_facility("Bumping Lake Campground Area")) is True

    def test_camp_recreation_site_passes(self):
        """'Camp Creek Recreation Site' has positive signal despite 'recreation site' pattern."""
        assert is_campground(_facility("Camp Creek Recreation Site")) is True

    def test_plain_campground_passes(self):
        assert is_campground(_facility("Ohanapecosh Campground")) is True

    def test_group_camp_passes(self):
        assert is_campground(_facility("Tulalip Group Camp")) is True


class TestExclusionFilter:
    """Names without 'campground'/'camp' are still filtered by EXCLUDE_PATTERNS."""

    def test_picnic_shelter_excluded(self):
        assert is_campground(_facility("Riverside Picnic Shelter")) is False

    def test_kitchen_excluded(self):
        assert is_campground(_facility("Paradise Kitchen")) is False

    def test_day_use_excluded(self):
        assert is_campground(_facility("Lakeview Day Use")) is False

    def test_boat_ramp_excluded(self):
        assert is_campground(_facility("Harbor Boat Ramp")) is False

    def test_scenic_byway_excluded(self):
        assert is_campground(_facility("Cascade Loop Scenic Byway")) is False

    def test_trailhead_excluded(self):
        assert is_campground(_facility("Summit Trailhead")) is False


class TestCoordinateAndBoundsChecks:
    """Facilities must have valid PNW coordinates."""

    def test_zero_coords_excluded(self):
        assert is_campground(_facility("Good Campground", lat=0.0, lon=0.0)) is False

    def test_out_of_bounds_excluded(self):
        """Florida coordinates should be excluded."""
        assert is_campground(_facility("Some Campground", lat=28.0, lon=-82.0)) is False

    def test_disabled_excluded(self):
        assert is_campground(_facility("Test Campground", enabled=False)) is False

    def test_valid_pnw_campground_passes(self):
        assert is_campground(_facility("Alpine Meadow", lat=47.5, lon=-121.5)) is True
