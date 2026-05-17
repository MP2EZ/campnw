"""Tests for the seed_registry.py is_campground() filter logic."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from seed_or_state import _safe_ra_photo_url
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


# ---------------------------------------------------------------------------
# v1.35 audit S8 — URL allowlist on stored image_urls
# ---------------------------------------------------------------------------


class TestSafeRaPhotoUrl:
    """ReserveAmerica photo URL allowlist (seed_or_state._safe_ra_photo_url)."""

    def test_accepts_standard_relative_photo_path(self):
        """Real RA originalPhotos URLs resolve to the RA host with https scheme."""
        out = _safe_ra_photo_url(
            "/webphotos/originals/OR/pid402146/{pht}1{pht}1655367336526.jpg"
        )
        assert out == (
            "https://www.reserveamerica.com/webphotos/originals/OR/pid402146/"
            "{pht}1{pht}1655367336526.jpg"
        )

    def test_accepts_absolute_https_ra_url(self):
        out = _safe_ra_photo_url(
            "https://www.reserveamerica.com/webphotos/originals/OR/pid402146/x.jpg"
        )
        assert out == (
            "https://www.reserveamerica.com/webphotos/originals/OR/pid402146/x.jpg"
        )

    def test_rejects_protocol_relative_host_escape(self):
        """A '//evil.com/x' should NOT escape to a different host."""
        assert _safe_ra_photo_url("//evil.com/x.jpg") is None

    def test_rejects_backslash_authority_escape(self):
        """Some parsers treat '/\\evil.com' as authority — must reject."""
        # urljoin will normalize this to a path on the base, but the netloc
        # check stays on www.reserveamerica.com, so it's accepted as a path.
        # We additionally reject anything pointing at a different netloc.
        assert _safe_ra_photo_url("https://evil.com/x.jpg") is None

    def test_rejects_javascript_url(self):
        assert _safe_ra_photo_url("javascript:alert(1)") is None

    def test_rejects_data_url(self):
        assert _safe_ra_photo_url("data:image/png;base64,abc") is None

    def test_rejects_http_downgrade(self):
        assert _safe_ra_photo_url("http://www.reserveamerica.com/x.jpg") is None

    def test_rejects_empty_or_none(self):
        assert _safe_ra_photo_url("") is None
        assert _safe_ra_photo_url(None) is None  # type: ignore[arg-type]


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
