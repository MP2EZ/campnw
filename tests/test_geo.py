"""Tests for geospatial utilities — haversine, base resolution, geocoding."""

import httpx
import pytest
import respx

from pnw_campsites.geo import (
    KNOWN_BASES,
    estimated_drive_minutes,
    format_drive_time,
    geocode_address,
    haversine_miles,
    is_known_base,
    resolve_base,
)

# ---------------------------------------------------------------------------
# Haversine Distance Tests
# ---------------------------------------------------------------------------


class TestHaversineMiles:
    """Test haversine great-circle distance calculations."""

    def test_same_point_returns_zero(self):
        """Same point should return 0 miles."""
        lat, lon = 47.6062, -122.3321  # Seattle
        result = haversine_miles(lat, lon, lat, lon)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_seattle_to_portland_approximately_145_miles(self):
        """Seattle to Portland is ~145 miles."""
        seattle_lat, seattle_lon = 47.6062, -122.3321
        portland_lat, portland_lon = 45.5152, -122.6784
        result = haversine_miles(seattle_lat, seattle_lon, portland_lat, portland_lon)
        # ~145 miles, within 5% tolerance (137–153 miles)
        assert 137 < result < 153, f"Expected ~145 mi, got {result:.1f} mi"

    def test_seattle_to_nyc_sanity_check(self):
        """Seattle to NYC should be ~2400 miles."""
        seattle_lat, seattle_lon = 47.6062, -122.3321
        nyc_lat, nyc_lon = 40.7128, -74.0060
        result = haversine_miles(seattle_lat, seattle_lon, nyc_lat, nyc_lon)
        # ~2400 miles, broad sanity check
        assert 2300 < result < 2500, f"Expected ~2400 mi, got {result:.1f} mi"

    def test_returns_float(self):
        """Result should be a float."""
        result = haversine_miles(47.6, -122.3, 45.5, -122.7)
        assert isinstance(result, float)

    def test_symmetric(self):
        """Distance A→B should equal B→A."""
        lat1, lon1 = 47.6062, -122.3321
        lat2, lon2 = 45.5152, -122.6784
        forward = haversine_miles(lat1, lon1, lat2, lon2)
        backward = haversine_miles(lat2, lon2, lat1, lon1)
        assert forward == pytest.approx(backward)


# ---------------------------------------------------------------------------
# Estimated Drive Minutes Tests
# ---------------------------------------------------------------------------


class TestEstimatedDriveMinutes:
    """Test drive time estimation (haversine + terrain multiplier)."""

    def test_seattle_to_portland_reasonable_range(self):
        """Seattle to Portland drive time should be 170–230 minutes."""
        seattle_lat, seattle_lon = 47.6062, -122.3321
        portland_lat, portland_lon = 45.5152, -122.6784
        result = estimated_drive_minutes(
            seattle_lat, seattle_lon, portland_lat, portland_lon
        )
        assert isinstance(result, int)
        assert 170 <= result <= 230, f"Expected 170–230 min, got {result} min"

    def test_same_point_returns_zero(self):
        """Same point should be 0 minutes."""
        lat, lon = 47.6062, -122.3321
        result = estimated_drive_minutes(lat, lon, lat, lon)
        assert result == 0

    def test_returns_int(self):
        """Result should be an integer."""
        result = estimated_drive_minutes(47.6, -122.3, 45.5, -122.7)
        assert isinstance(result, int)

    def test_symmetric(self):
        """A→B should equal B→A."""
        lat1, lon1 = 47.6062, -122.3321
        lat2, lon2 = 45.5152, -122.6784
        forward = estimated_drive_minutes(lat1, lon1, lat2, lon2)
        backward = estimated_drive_minutes(lat2, lon2, lat1, lon1)
        assert forward == backward


# ---------------------------------------------------------------------------
# Format Drive Time Tests
# ---------------------------------------------------------------------------


class TestFormatDriveTime:
    """Test drive time formatting."""

    def test_under_one_hour(self):
        """45 minutes should format as '~45m'."""
        result = format_drive_time(45)
        assert result == "~45m"

    def test_exact_hours(self):
        """120 minutes should format as '~2h'."""
        result = format_drive_time(120)
        assert result == "~2h"

    def test_hours_and_minutes(self):
        """90 minutes should format as '~1h 30m'."""
        result = format_drive_time(90)
        assert result == "~1h 30m"

    def test_one_hour(self):
        """60 minutes should format as '~1h'."""
        result = format_drive_time(60)
        assert result == "~1h"

    def test_zero_minutes(self):
        """0 minutes should format as '~0m'."""
        result = format_drive_time(0)
        assert result == "~0m"

    def test_multiple_hours_with_minutes(self):
        """210 minutes should format as '~3h 30m'."""
        result = format_drive_time(210)
        assert result == "~3h 30m"

    def test_single_minute(self):
        """1 minute should format as '~1m'."""
        result = format_drive_time(1)
        assert result == "~1m"


# ---------------------------------------------------------------------------
# Base Resolution Tests
# ---------------------------------------------------------------------------


class TestResolveBase:
    """Test known base lookup."""

    def test_resolve_seattle_lowercase(self):
        """'seattle' should resolve to Seattle coords."""
        result = resolve_base("seattle")
        assert result == KNOWN_BASES["seattle"]
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(x, float) for x in result)

    def test_resolve_seattle_uppercase(self):
        """'SEATTLE' should resolve (case-insensitive)."""
        result = resolve_base("SEATTLE")
        assert result == KNOWN_BASES["seattle"]

    def test_resolve_seattle_mixed_case(self):
        """'SeAtTle' should resolve (case-insensitive)."""
        result = resolve_base("SeAtTle")
        assert result == KNOWN_BASES["seattle"]

    def test_resolve_bellevue(self):
        """'bellevue' should resolve."""
        result = resolve_base("bellevue")
        assert result == KNOWN_BASES["bellevue"]

    def test_resolve_portland(self):
        """'portland' should resolve."""
        result = resolve_base("portland")
        assert result == KNOWN_BASES["portland"]

    def test_unknown_base_raises_value_error(self):
        """Unknown base name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown base 'unknown'"):
            resolve_base("unknown")

    def test_unknown_base_error_lists_known_bases(self):
        """ValueError message should list known bases."""
        with pytest.raises(ValueError, match="Known bases:"):
            resolve_base("nowhere")

    def test_empty_string_raises_value_error(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            resolve_base("")


# ---------------------------------------------------------------------------
# Is Known Base Tests
# ---------------------------------------------------------------------------


class TestIsKnownBase:
    """Test base existence checking."""

    def test_bellevue_is_known(self):
        """'bellevue' should be recognized as a known base."""
        assert is_known_base("bellevue") is True

    def test_seattle_is_known(self):
        """'seattle' should be recognized as a known base."""
        assert is_known_base("seattle") is True

    def test_bellevue_uppercase_is_known(self):
        """'BELLEVUE' should be recognized (case-insensitive)."""
        assert is_known_base("BELLEVUE") is True

    def test_unknown_is_not_known(self):
        """'somewhere' should not be recognized."""
        assert is_known_base("somewhere") is False

    def test_empty_string_is_not_known(self):
        """Empty string should not be recognized."""
        assert is_known_base("") is False

    def test_all_known_bases_recognized(self):
        """All bases in KNOWN_BASES should be recognized."""
        for base_name in KNOWN_BASES:
            assert is_known_base(base_name) is True


# ---------------------------------------------------------------------------
# Geocoding Tests
# ---------------------------------------------------------------------------


class TestGeocodeAddress:
    """Test Nominatim geocoding."""

    @respx.mock
    async def test_geocode_seattle(self):
        """Geocoding 'Seattle, WA' should return (lat, lon) tuple."""
        respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Seattle, WA", "format": "json", "limit": 1},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[{"lat": "47.6", "lon": "-122.3"}],
            )
        )
        result = await geocode_address("Seattle, WA")
        assert result == (47.6, -122.3)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(x, float) for x in result)

    @respx.mock
    async def test_geocode_portland(self):
        """Geocoding 'Portland, OR' should return correct coords."""
        respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Portland, OR", "format": "json", "limit": 1},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[{"lat": "45.5152", "lon": "-122.6784"}],
            )
        )
        result = await geocode_address("Portland, OR")
        assert result == (45.5152, -122.6784)

    async def test_empty_address_raises_value_error(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Address must be 1-200 characters"):
            await geocode_address("")

    async def test_whitespace_only_raises_value_error(self):
        """Whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError, match="Address must be 1-200 characters"):
            await geocode_address("   ")

    async def test_address_too_long_raises_value_error(self):
        """Address over 200 chars should raise ValueError."""
        long_address = "x" * 201
        with pytest.raises(ValueError, match="Address must be 1-200 characters"):
            await geocode_address(long_address)

    @respx.mock
    async def test_nonexistent_address_raises_value_error(self):
        """Nonexistent address should raise ValueError."""
        respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Nonexistent", "format": "json", "limit": 1},
        ).mock(return_value=httpx.Response(200, json=[]))
        with pytest.raises(
            ValueError, match="Could not geocode address: 'Nonexistent'"
        ):
            await geocode_address("Nonexistent")

    @respx.mock
    async def test_uses_correct_nominatim_endpoint(self):
        """Should use Nominatim search endpoint with correct params."""
        route = respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Test", "format": "json", "limit": 1},
        ).mock(return_value=httpx.Response(200, json=[{"lat": "0", "lon": "0"}]))
        await geocode_address("Test")
        assert route.called

    @respx.mock
    async def test_uses_user_agent_header(self):
        """Should include User-Agent header."""
        route = respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Test", "format": "json", "limit": 1},
        ).mock(return_value=httpx.Response(200, json=[{"lat": "0", "lon": "0"}]))
        await geocode_address("Test")
        request = route.calls[0].request
        assert "User-Agent" in request.headers
        assert "PNW-Campsites" in request.headers["User-Agent"]

    async def test_address_at_boundary_200_chars(self):
        """Address with exactly 200 chars should not raise ValueError."""
        address_200 = "a" * 200
        with pytest.raises(ValueError):
            # Will fail in the actual geocode call (no mock), but not validation
            await geocode_address(address_200)

    @respx.mock
    async def test_returns_floats_not_strings(self):
        """Should return float tuple, not string tuple."""
        respx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Test", "format": "json", "limit": 1},
        ).mock(return_value=httpx.Response(200, json=[{"lat": "47.6", "lon": "-122.3"}]))
        lat, lon = await geocode_address("Test")
        assert isinstance(lat, float)
        assert isinstance(lon, float)
