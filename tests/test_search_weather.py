"""Tests for weather enrichment in search responses."""

from datetime import date

from pnw_campsites.routes.search import _lookup_weather_single, _weather_date


def test_weather_date_midpoint():
    """Midpoint (month, day) is calculated correctly."""
    # June 1 to June 30 -> midpoint ~June 15
    m, d = _weather_date(date(2026, 6, 1), date(2026, 6, 30))
    assert m == 6
    assert d == 15

    # June 15 to July 15 -> midpoint ~June 30
    m, d = _weather_date(date(2026, 6, 15), date(2026, 7, 15))
    assert m == 6
    assert d == 30

    # Single day: July 4 to July 4
    m, d = _weather_date(date(2026, 7, 4), date(2026, 7, 4))
    assert m == 7
    assert d == 4


def test_lookup_weather_single_zero_coords():
    """Campgrounds with 0,0 coordinates return None."""
    result = _lookup_weather_single(0.0, 0.0, date(2026, 7, 1), date(2026, 7, 7))
    assert result is None


def test_lookup_weather_single_uncached(tmp_path):
    """Uncached location returns None gracefully."""
    from unittest.mock import MagicMock, patch

    from pnw_campsites.registry.db import CampgroundRegistry

    reg = CampgroundRegistry(tmp_path / "registry.db")
    mock_get_registry = MagicMock(return_value=reg)

    with patch("pnw_campsites.routes.search.get_registry", mock_get_registry):
        result = _lookup_weather_single(
            47.61, -122.33, date(2026, 7, 1), date(2026, 7, 7)
        )
    assert result is None
    reg.close()


def test_lookup_weather_single_cached(tmp_path):
    """Cached weather is returned correctly."""
    from unittest.mock import MagicMock, patch

    from pnw_campsites.registry.db import CampgroundRegistry

    reg = CampgroundRegistry(tmp_path / "registry.db")
    reg.upsert_weather_normals([{
        "lat_2dp": 47.61, "lon_2dp": -122.33, "month": 7, "day": 15,
        "temp_high_f": 75.0, "temp_low_f": 55.0, "precip_pct": 10.0,
        "fetched_at": "2026-04-15T00:00:00Z",
    }])
    mock_get_registry = MagicMock(return_value=reg)

    with patch("pnw_campsites.routes.search.get_registry", mock_get_registry):
        # Search midpoint July 4 → closest cached is July 15
        result = _lookup_weather_single(
            47.61, -122.33, date(2026, 7, 1), date(2026, 7, 7)
        )
    assert result is not None
    high, low, precip = result
    assert high == 75.0
    assert low == 55.0
    reg.close()
