"""Tests for weather normals cache in CampgroundRegistry."""

from pathlib import Path

import pytest

from pnw_campsites.registry.db import CampgroundRegistry


@pytest.fixture
def registry(tmp_path: Path) -> CampgroundRegistry:
    reg = CampgroundRegistry(tmp_path / "registry.db")
    yield reg
    reg.close()


def _make_row(lat=47.61, lon=-122.33, month=7, day=15, high=75.0, low=55.0, precip=10.0):
    return {
        "lat_2dp": lat, "lon_2dp": lon, "month": month, "day": day,
        "temp_high_f": high, "temp_low_f": low, "precip_pct": precip,
        "fetched_at": "2026-04-15T00:00:00Z",
    }


def test_get_weather_normals_empty(registry: CampgroundRegistry):
    """Returns None for uncached location."""
    result = registry.get_weather_normals(47.61, -122.33, 7, 15)
    assert result is None


def test_upsert_and_get_roundtrip(registry: CampgroundRegistry):
    """Upserted normals are retrievable."""
    registry.upsert_weather_normals([_make_row(high=75.2, low=55.1, precip=8.3)])

    result = registry.get_weather_normals(47.61, -122.33, 7, 15)
    assert result is not None
    high, low, precip = result
    assert high == pytest.approx(75.2)
    assert low == pytest.approx(55.1)
    assert precip == pytest.approx(8.3)


def test_coordinate_rounding(registry: CampgroundRegistry):
    """Lat/lon are rounded to 2 decimal places for cache key."""
    registry.upsert_weather_normals([_make_row()])

    # Query with unrounded coordinates that round to the same 2dp
    result = registry.get_weather_normals(47.6062, -122.3321, 7, 15)
    assert result is not None


def test_closest_day_single_sample(registry: CampgroundRegistry):
    """With only day 15 cached, querying day 3 returns day 15's data."""
    registry.upsert_weather_normals([_make_row(day=15, high=75.0)])

    result = registry.get_weather_normals(47.61, -122.33, 7, 3)
    assert result is not None
    assert result[0] == pytest.approx(75.0)


def test_closest_day_picks_nearer(registry: CampgroundRegistry):
    """With days 1 and 15 cached, querying day 3 returns day 1's data."""
    registry.upsert_weather_normals([
        _make_row(day=1, high=68.0),
        _make_row(day=15, high=75.0),
    ])

    result = registry.get_weather_normals(47.61, -122.33, 7, 3)
    assert result is not None
    assert result[0] == pytest.approx(68.0)  # day 1 is closer to day 3


def test_batch_lookup_closest_day(registry: CampgroundRegistry):
    """Batch lookup picks closest day per location."""
    registry.upsert_weather_normals([
        _make_row(day=1, high=68.0),
        _make_row(day=15, high=75.0),
    ])

    locations = [(47.61, -122.33, 7, 5)]  # day 5 → closest is day 1
    result = registry.get_weather_normals_batch(locations)
    key = (47.61, -122.33, 7)
    assert key in result
    assert result[key][0] == pytest.approx(68.0)


def test_batch_lookup_mixed_cached_uncached(registry: CampgroundRegistry):
    """Batch returns cached entries, skips uncached."""
    registry.upsert_weather_normals([_make_row()])

    locations = [
        (47.61, -122.33, 7, 15),   # cached
        (45.50, -121.00, 7, 15),   # not cached
    ]
    result = registry.get_weather_normals_batch(locations)
    assert (47.61, -122.33, 7) in result
    assert (45.50, -121.00, 7) not in result


def test_upsert_overwrites(registry: CampgroundRegistry):
    """Upserting same key updates the values."""
    registry.upsert_weather_normals([_make_row(high=70.0)])
    registry.upsert_weather_normals([_make_row(high=80.0)])

    result = registry.get_weather_normals(47.61, -122.33, 7, 15)
    assert result[0] == pytest.approx(80.0)


def test_count_cached_normals(registry: CampgroundRegistry):
    """Counts months cached for a specific day."""
    rows = [_make_row(month=m, day=15) for m in range(4, 11)]  # 7 months
    registry.upsert_weather_normals(rows)

    assert registry.count_cached_normals(47.61, -122.33, 15) == 7
    assert registry.count_cached_normals(47.61, -122.33, 1) == 0  # different day
    assert registry.count_cached_normals(99.0, 99.0, 15) == 0  # different location
