"""Booking URL construction for supported reservation systems."""

from __future__ import annotations

from datetime import date

RA_BASE_URL = "https://www.reserveamerica.com"


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


# ---------------------------------------------------------------------------
# WA State Parks (GoingToCamp)
# ---------------------------------------------------------------------------


def wa_state_park_url(resource_location_id: str) -> str:
    """URL for a WA State Park on GoingToCamp."""
    return (
        f"https://washington.goingtocamp.com/create-booking/results"
        f"?resourceLocationId={resource_location_id}"
    )


def wa_state_availability_url(
    resource_location_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """Deep link to a WA State Park's availability on GoingToCamp."""
    url = (
        f"https://washington.goingtocamp.com/create-booking/results"
        f"?resourceLocationId={resource_location_id}"
    )
    if start_date:
        url += f"&searchTime={start_date.isoformat()}"
    if end_date:
        url += f"&endDate={end_date.isoformat()}"
    return url


# ---------------------------------------------------------------------------
# OR State Parks (ReserveAmerica)
# ---------------------------------------------------------------------------


def or_state_availability_url(
    park_id: str,
    slug: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """Deep link to an OR State Park's availability on ReserveAmerica.

    Only passes arrivalDate (positions the 14-day calendar grid).
    RA treats departureDate as a booking checkout date, not a viewing
    window — passing our full search range would imply a multi-month stay.
    """
    url = f"{RA_BASE_URL}/explore/{slug}/OR/{park_id}/campsite-availability"
    if start_date:
        url += f"?arrivalDate={start_date.isoformat()}"
    return url
