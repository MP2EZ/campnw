"""Mapbox Directions + Matrix API client for accurate drive times."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("pnw_campsites.mapbox")

DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving"
MATRIX_URL = "https://api.mapbox.com/directions-matrix/v1/mapbox/driving"
MATRIX_MAX_COORDS = 25  # Mapbox limit per request (including the origin)
BATCH_DELAY = 1.0  # seconds between Matrix API calls
MAX_RETRIES = 5


def _get_token() -> str:
    token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("MAPBOX_ACCESS_TOKEN not set")
    return token


def _ll(lat: float, lon: float) -> str:
    """Format as Mapbox coordinate string (lon,lat order)."""
    return f"{lon},{lat}"


async def get_drive_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict:
    """Single origin -> destination drive time via Directions API.

    Args:
        origin: (lat, lon)
        destination: (lat, lon)

    Returns:
        {"drive_minutes": int, "drive_miles": float}

    Raises:
        RuntimeError: if no token set
        httpx.HTTPStatusError: on API error
        ValueError: if no route found
    """
    token = _get_token()
    coords = f"{_ll(*origin)};{_ll(*destination)}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DIRECTIONS_URL}/{coords}",
            params={"access_token": token, "overview": "false"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        raise ValueError(
            f"No route found from {origin} to {destination}"
        )

    route = routes[0]
    return {
        "drive_minutes": round(route["duration"] / 60),
        "drive_miles": round(route["distance"] / 1609.34, 1),
    }


async def get_drive_times_matrix(
    origin: tuple[float, float],
    destinations: list[tuple[str, float, float]],
) -> dict[str, dict]:
    """Batch origin -> destinations via Matrix API.

    Auto-chunks into batches of 24 destinations (25 coords including origin).

    Args:
        origin: (lat, lon)
        destinations: list of (facility_id, lat, lon)

    Returns:
        {facility_id: {"drive_minutes": int, "drive_miles": float}}
        Destinations with no route are omitted.
    """
    if not destinations:
        return {}

    token = _get_token()
    results: dict[str, dict] = {}
    chunk_size = MATRIX_MAX_COORDS - 1  # reserve slot 0 for origin

    for i in range(0, len(destinations), chunk_size):
        chunk = destinations[i : i + chunk_size]

        # Build coordinate string: origin first, then destinations
        coord_parts = [_ll(*origin)]
        for _fid, lat, lon in chunk:
            coord_parts.append(_ll(lat, lon))
        coords_str = ";".join(coord_parts)

        for attempt in range(MAX_RETRIES):
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{MATRIX_URL}/{coords_str}",
                    params={
                        "access_token": token,
                        "sources": "0",
                        "annotations": "duration,distance",
                    },
                    timeout=30.0,
                )
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Matrix API rate limited, retrying in %ds", wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()  # raise after max retries
        data = resp.json()

        durations = data.get("durations", [[]])[0]  # row 0 = from origin
        distances = data.get("distances", [[]])[0]

        for j, (fid, _lat, _lon) in enumerate(chunk):
            # durations[0] is origin-to-origin, destinations start at index 1
            dur = durations[j + 1] if j + 1 < len(durations) else None
            dist = distances[j + 1] if j + 1 < len(distances) else None
            if dur is not None:
                results[fid] = {
                    "drive_minutes": round(dur / 60),
                    "drive_miles": round(dist / 1609.34, 1) if dist else None,
                }

        # Rate-limit courtesy delay between batches
        if i + chunk_size < len(destinations):
            await asyncio.sleep(BATCH_DELAY)

    return results
