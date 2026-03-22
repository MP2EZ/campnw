"""Geospatial utilities — haversine distance, known bases, geocoding."""

from __future__ import annotations

import math

import httpx

# ---------------------------------------------------------------------------
# Known base locations (lat, lon)
# ---------------------------------------------------------------------------

KNOWN_BASES: dict[str, tuple[float, float]] = {
    "seattle": (47.6062, -122.3321),
    "bellevue": (47.6101, -122.2015),
    "portland": (45.5152, -122.6784),
    "spokane": (47.6588, -117.4260),
    "bellingham": (48.7519, -122.4787),
    "moscow": (46.7324, -117.0002),
}

# PNW terrain makes straight-line distance misleading (mountains, water).
# 1.4x multiplier on haversine approximates actual drive distance.
DRIVE_DISTANCE_MULTIPLIER = 1.4
AVERAGE_SPEED_MPH = 55

EARTH_RADIUS_MILES = 3958.8


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def estimated_drive_minutes(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> int:
    """Approximate drive time in minutes using haversine + terrain multiplier."""
    miles = haversine_miles(lat1, lon1, lat2, lon2) * DRIVE_DISTANCE_MULTIPLIER
    return round(miles / AVERAGE_SPEED_MPH * 60)


def format_drive_time(minutes: int) -> str:
    """Format minutes as '~Xh Ym'."""
    h, m = divmod(minutes, 60)
    if h == 0:
        return f"~{m}m"
    if m == 0:
        return f"~{h}h"
    return f"~{h}h {m}m"


# ---------------------------------------------------------------------------
# Base resolution
# ---------------------------------------------------------------------------


def resolve_base(name: str) -> tuple[float, float]:
    """Look up a known base by name (case-insensitive).

    Raises ValueError if not a known base.
    """
    coords = KNOWN_BASES.get(name.lower())
    if coords is None:
        raise ValueError(
            f"Unknown base '{name}'. "
            f"Known bases: {', '.join(KNOWN_BASES.keys())}"
        )
    return coords


def is_known_base(name: str) -> bool:
    return name.lower() in KNOWN_BASES


# ---------------------------------------------------------------------------
# Geocoding (Nominatim — free, no API key, 1 req/sec)
# ---------------------------------------------------------------------------


async def geocode_address(address: str) -> tuple[float, float]:
    """Geocode an address via Nominatim. Returns (lat, lon).

    Raises ValueError if the address can't be resolved.
    """
    if not address.strip() or len(address) > 200:
        raise ValueError("Address must be 1-200 characters")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "PNW-Campsites/1.0 (personal camping tool)"},
            timeout=10.0,
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        raise ValueError(f"Could not geocode address: '{address}'")

    return float(results[0]["lat"]), float(results[0]["lon"])
