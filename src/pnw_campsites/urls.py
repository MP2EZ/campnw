"""Booking URL construction for supported reservation systems."""

from __future__ import annotations

from datetime import date


def recgov_campground_url(facility_id: str) -> str:
    """URL for a campground's page on recreation.gov."""
    return f"https://www.recreation.gov/camping/campgrounds/{facility_id}"


def recgov_availability_url(facility_id: str, start_date: date | None = None) -> str:
    """Deep link to a campground's availability calendar on recreation.gov."""
    url = f"https://www.recreation.gov/camping/campgrounds/{facility_id}/availability"
    if start_date:
        url += f"?startDate={start_date.isoformat()}"
    return url


def recgov_campsite_booking_url(
    facility_id: str,
    campsite_id: str,
    start_date: date,
    end_date: date,
) -> str:
    """Deep link to book a specific campsite on recreation.gov."""
    return (
        f"https://www.recreation.gov/camping/campsites/{campsite_id}"
        f"?startDate={start_date.isoformat()}"
        f"&endDate={end_date.isoformat()}"
        f"&facilityId={facility_id}"
    )
