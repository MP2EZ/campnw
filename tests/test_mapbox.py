"""Tests for Mapbox Directions + Matrix API client."""

import httpx
import pytest
import respx

from pnw_campsites.mapbox import (
    DIRECTIONS_URL,
    MATRIX_MAX_COORDS,
    MATRIX_URL,
    _ll,
    get_drive_time,
    get_drive_times_matrix,
)

# ---------------------------------------------------------------------------
# Coordinate formatting
# ---------------------------------------------------------------------------


class TestCoordinateFormatting:
    def test_ll_formats_lon_lat_order(self):
        """Mapbox uses lon,lat — verify our helper swaps correctly."""
        assert _ll(47.6, -122.3) == "-122.3,47.6"

    def test_ll_preserves_precision(self):
        result = _ll(47.6062, -122.3321)
        assert result == "-122.3321,47.6062"


# ---------------------------------------------------------------------------
# Directions API (single route)
# ---------------------------------------------------------------------------


class TestGetDriveTime:
    @respx.mock
    async def test_seattle_to_portland(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(DIRECTIONS_URL + "/-122.3321,47.6062;-122.6784,45.5152").mock(
            return_value=httpx.Response(
                200,
                json={
                    "routes": [
                        {"duration": 10200, "distance": 280000}  # 170 min, ~174 mi
                    ]
                },
            )
        )
        result = await get_drive_time((47.6062, -122.3321), (45.5152, -122.6784))
        assert result["drive_minutes"] == 170
        assert result["drive_miles"] == pytest.approx(173.9, abs=0.5)

    @respx.mock
    async def test_no_route_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(DIRECTIONS_URL + "/-122.3,47.6;-122.7,45.5").mock(
            return_value=httpx.Response(200, json={"routes": []})
        )
        with pytest.raises(ValueError, match="No route found"):
            await get_drive_time((47.6, -122.3), (45.5, -122.7))

    async def test_no_token_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="MAPBOX_ACCESS_TOKEN not set"):
            await get_drive_time((47.6, -122.3), (45.5, -122.7))

    @respx.mock
    async def test_api_error_raises(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(DIRECTIONS_URL + "/-122.3,47.6;-122.7,45.5").mock(
            return_value=httpx.Response(401, json={"message": "Not Authorized"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await get_drive_time((47.6, -122.3), (45.5, -122.7))

    @respx.mock
    async def test_rounds_minutes(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(DIRECTIONS_URL + "/-122.3,47.6;-122.7,45.5").mock(
            return_value=httpx.Response(
                200,
                json={"routes": [{"duration": 5430, "distance": 150000}]},  # 90.5 min
            )
        )
        result = await get_drive_time((47.6, -122.3), (45.5, -122.7))
        assert result["drive_minutes"] == 90  # round(90.5) = 90


# ---------------------------------------------------------------------------
# Matrix API (batch)
# ---------------------------------------------------------------------------


class TestGetDriveTimesMatrix:
    @respx.mock
    async def test_single_destination(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(MATRIX_URL + "/-122.3,47.6;-122.7,45.5").mock(
            return_value=httpx.Response(
                200,
                json={
                    "durations": [[0, 10200]],
                    "distances": [[0, 280000]],
                },
            )
        )
        result = await get_drive_times_matrix(
            (47.6, -122.3),
            [("park-1", 45.5, -122.7)],
        )
        assert "park-1" in result
        assert result["park-1"]["drive_minutes"] == 170

    @respx.mock
    async def test_multiple_destinations(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(MATRIX_URL + "/-122.3,47.6;-122.7,45.5;-121.3,44.1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "durations": [[0, 10200, 18000]],
                    "distances": [[0, 280000, 500000]],
                },
            )
        )
        result = await get_drive_times_matrix(
            (47.6, -122.3),
            [("park-1", 45.5, -122.7), ("park-2", 44.1, -121.3)],
        )
        assert len(result) == 2
        assert result["park-1"]["drive_minutes"] == 170
        assert result["park-2"]["drive_minutes"] == 300

    @respx.mock
    async def test_null_duration_omitted(self, monkeypatch):
        """Destinations with no route (null duration) should be omitted."""
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        respx.get(MATRIX_URL + "/-122.3,47.6;-122.7,45.5;-121.3,44.1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "durations": [[0, None, 18000]],
                    "distances": [[0, None, 500000]],
                },
            )
        )
        result = await get_drive_times_matrix(
            (47.6, -122.3),
            [("park-1", 45.5, -122.7), ("park-2", 44.1, -121.3)],
        )
        assert "park-1" not in result
        assert "park-2" in result

    async def test_empty_destinations(self, monkeypatch):
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")
        result = await get_drive_times_matrix((47.6, -122.3), [])
        assert result == {}

    @respx.mock
    async def test_chunking_at_boundary(self, monkeypatch):
        """Should chunk at MATRIX_MAX_COORDS - 1 destinations per batch."""
        monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test")

        # MATRIX_MAX_COORDS dests → 2 batches: (MAX-1) + 1
        n_dests = MATRIX_MAX_COORDS
        destinations = [
            (f"park-{i}", 45.0 + i * 0.01, -122.0) for i in range(n_dests)
        ]

        call_count = 0

        def make_response(request):
            nonlocal call_count
            call_count += 1
            # Count coords in URL to determine batch size
            coord_pairs = str(request.url.path).split(MATRIX_URL.split("mapbox.com")[1])[1]
            n_coords = len(coord_pairs.strip("/").split(";"))
            # durations[0] = row from origin, length = n_coords
            durations = [0] + [3600 * i for i in range(1, n_coords)]
            distances = [0] + [100000 * i for i in range(1, n_coords)]
            return httpx.Response(
                200,
                json={"durations": [durations], "distances": [distances]},
            )

        respx.route(method="GET", url__startswith=MATRIX_URL).mock(side_effect=make_response)

        result = await get_drive_times_matrix((47.6, -122.3), destinations)
        assert call_count == 2
        assert len(result) == n_dests
