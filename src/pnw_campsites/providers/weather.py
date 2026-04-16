"""Visual Crossing Weather API client — climate normals for campground locations."""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger("pnw_campsites.weather")

BASE_URL = (
    "https://weather.visualcrossing.com/VisualCrossingWebServices"
    "/rest/services/timeline"
)

SEASON_MONTHS = list(range(4, 11))  # Apr-Oct


class VisualCrossingClient:
    """Async client for Visual Crossing Timeline API.

    Fetches statistical climate normals via individual single-day queries.
    Each query costs 1 record against the free-tier quota (1,000/day).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> VisualCrossingClient:
        self._client = httpx.AsyncClient(timeout=15.0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_normals(
        self, lat: float, lon: float, targets: list[tuple[int, int]],
    ) -> tuple[list[dict], bool]:
        """Fetch climate normals for specific (month, day) pairs.

        Uses include=stats to get multi-year statistical averages.
        Each single-day query costs 1 record against the daily quota.

        Returns (results, was_rate_limited). Each result:
            {month, day, temp_high_f, temp_low_f, precip_pct}
        On 429: returns partial results collected so far + True.
        """
        assert self._client is not None, "Use as async context manager"
        results = []
        for i, (month, day) in enumerate(targets):
            if i > 0:
                await asyncio.sleep(1.0)
            date_str = f"2025-{month:02d}-{day:02d}"
            url = f"{BASE_URL}/{lat},{lon}/{date_str}/{date_str}"
            params = {
                "unitGroup": "us",
                "include": "stats",
                "key": self._api_key,
                "elements": "datetime,tempmax,tempmin,precipprob",
            }
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 429:
                    # Could be burst rate limit — wait 60s and retry once
                    logger.warning("429 hit — pausing 60s before retry...")
                    print("  [429] pausing 60s ...", end="", flush=True)
                    await asyncio.sleep(60)
                    resp = await self._client.get(url, params=params)
                    if resp.status_code == 429:
                        print(" still limited, stopping.")
                        return results, True
                    print(" resumed.")
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Visual Crossing API error for (%s, %s): HTTP %s",
                    lat, lon, exc.response.status_code,
                )
                continue
            except httpx.RequestError as exc:
                logger.warning(
                    "Visual Crossing request failed for (%s, %s): %s",
                    lat, lon, type(exc).__name__,
                )
                continue

            data = resp.json()
            day_data = data.get("days", [{}])[0]
            normal = day_data.get("normal", {})

            # Prefer normal.tempmax[1] (statistical mean) when available
            high = (
                normal["tempmax"][1]
                if normal.get("tempmax") and len(normal["tempmax"]) >= 2
                else day_data.get("tempmax")
            )
            low = (
                normal["tempmin"][1]
                if normal.get("tempmin") and len(normal["tempmin"]) >= 2
                else day_data.get("tempmin")
            )
            precip = day_data.get("precipprob", 0.0)

            if high is not None and low is not None:
                results.append({
                    "month": month,
                    "day": day,
                    "temp_high_f": round(high, 1),
                    "temp_low_f": round(low, 1),
                    "precip_pct": round(precip, 1),
                })

        return results, False
