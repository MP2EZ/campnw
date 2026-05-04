"""Tests for Visual Crossing weather provider."""


import pytest
import respx
from httpx import Response

from pnw_campsites.providers.weather import BASE_URL, VisualCrossingClient


def _stats_response(month: int, day: int, high: float = 74.0, low: float = 57.8, precip: float = 5.0):
    """Build a single-day stats API response."""
    return Response(200, json={"days": [{
        "datetime": f"2025-{month:02d}-{day:02d}",
        "tempmax": high, "tempmin": low, "precipprob": precip,
        "normal": {
            "tempmax": [high - 10, high, high + 10],
            "tempmin": [low - 5, low, low + 5],
        },
    }]})


@respx.mock
async def test_fetch_normals_parses_stats():
    """Stats response with normal object is parsed correctly."""
    targets = [(7, 15)]
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-07-15/2025-07-15").mock(
        return_value=_stats_response(7, 15, high=74.0, low=57.8, precip=5.0)
    )

    async with VisualCrossingClient("test-key") as client:
        results, rate_limited = await client.fetch_normals(47.61, -122.33, targets)

    assert not rate_limited
    assert len(results) == 1
    assert results[0]["month"] == 7
    assert results[0]["day"] == 15
    assert results[0]["temp_high_f"] == pytest.approx(74.0)
    assert results[0]["temp_low_f"] == pytest.approx(57.8)
    assert results[0]["precip_pct"] == pytest.approx(5.0)


@respx.mock
async def test_fetch_multiple_targets():
    """Multiple (month, day) targets each get their own call."""
    targets = [(4, 15), (5, 15), (6, 15)]
    for m in [4, 5, 6]:
        respx.get(f"{BASE_URL}/47.61,-122.33/2025-{m:02d}-15/2025-{m:02d}-15").mock(
            return_value=_stats_response(m, 15, high=60.0 + m * 2)
        )

    async with VisualCrossingClient("test-key") as client:
        results, rate_limited = await client.fetch_normals(47.61, -122.33, targets)

    assert not rate_limited
    assert len(results) == 3
    assert results[0]["month"] == 4
    assert results[2]["month"] == 6


@respx.mock
async def test_429_returns_partial_results(monkeypatch):
    """On 429, waits and retries. If still 429, returns partial + rate_limited=True."""
    # Patch asyncio.sleep to avoid 60s wait in test
    async def _instant_sleep(_: float) -> None:
        pass
    monkeypatch.setattr("pnw_campsites.providers.weather.asyncio.sleep", _instant_sleep)

    targets = [(4, 15), (5, 15), (6, 15)]
    # Apr and May succeed, Jun hits 429 (both initial and retry)
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-04-15/2025-04-15").mock(
        return_value=_stats_response(4, 15)
    )
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-05-15/2025-05-15").mock(
        return_value=_stats_response(5, 15)
    )
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-06-15/2025-06-15").mock(
        return_value=Response(429, text="Rate limited")
    )

    async with VisualCrossingClient("test-key") as client:
        results, rate_limited = await client.fetch_normals(47.61, -122.33, targets)

    assert rate_limited
    assert len(results) == 2  # Apr + May, not Jun


@respx.mock
async def test_500_skips_and_continues():
    """Non-429 errors skip that target and continue."""
    targets = [(4, 15), (5, 15), (6, 15)]
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-04-15/2025-04-15").mock(
        return_value=_stats_response(4, 15)
    )
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-05-15/2025-05-15").mock(
        return_value=Response(500, text="Server Error")
    )
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-06-15/2025-06-15").mock(
        return_value=_stats_response(6, 15)
    )

    async with VisualCrossingClient("test-key") as client:
        results, rate_limited = await client.fetch_normals(47.61, -122.33, targets)

    assert not rate_limited
    assert len(results) == 2  # Apr + Jun, May skipped
    assert results[0]["month"] == 4
    assert results[1]["month"] == 6


@respx.mock
async def test_fallback_to_top_level_when_no_normal():
    """Falls back to top-level tempmax/tempmin when normal object is missing."""
    targets = [(6, 15)]
    respx.get(f"{BASE_URL}/47.61,-122.33/2025-06-15/2025-06-15").mock(
        return_value=Response(200, json={"days": [{
            "datetime": "2025-06-15",
            "tempmax": 70.0, "tempmin": 50.0, "precipprob": 10.0,
        }]})
    )

    async with VisualCrossingClient("test-key") as client:
        results, rate_limited = await client.fetch_normals(47.61, -122.33, targets)

    assert len(results) == 1
    assert results[0]["temp_high_f"] == pytest.approx(70.0)
