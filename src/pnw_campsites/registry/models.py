"""Data models for the campground registry and availability data."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Availability (matches rec.gov undocumented API response)
# ---------------------------------------------------------------------------


class AvailabilityStatus(StrEnum):
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    NOT_AVAILABLE = "Not Available"
    NOT_RESERVABLE = "Not Reservable"  # site exists but can't be reserved online
    NOT_RESERVABLE_MGMT = "Not Reservable Management"  # held by management
    NYR = "NYR"  # Not Yet Released — reservations haven't opened
    OPEN = "Open"  # FCFS / walk-in only
    CLOSED = "Closed"  # seasonal closure


class CampsiteAvailability(BaseModel):
    """Per-campsite availability from the rec.gov availability endpoint."""

    campsite_id: str
    site: str  # e.g. "D016"
    loop: str  # e.g. "A-F"
    campsite_type: str  # e.g. "STANDARD NONELECTRIC"
    type_of_use: str  # e.g. "Overnight"
    min_num_people: int  # can be 0
    max_num_people: int
    availabilities: dict[str, AvailabilityStatus]  # ISO datetime str -> status

    def available_dates(self) -> list[str]:
        """Return sorted list of dates with Available status."""
        return sorted(
            d for d, s in self.availabilities.items() if s == AvailabilityStatus.AVAILABLE
        )

    @property
    def is_fcfs(self) -> bool:
        """True if this site is FCFS — not bookable online."""
        statuses = set(self.availabilities.values())
        return not statuses.intersection(
            {AvailabilityStatus.AVAILABLE, AvailabilityStatus.RESERVED}
        ) and statuses.intersection(
            {AvailabilityStatus.NOT_RESERVABLE, AvailabilityStatus.OPEN}
        )


class CampgroundAvailability(BaseModel):
    """Full availability response for a campground (one month)."""

    facility_id: str
    campsites: dict[str, CampsiteAvailability]  # keyed by campsite_id (string)


# ---------------------------------------------------------------------------
# RIDB metadata (from official API)
# ---------------------------------------------------------------------------


class RIDBFacility(BaseModel):
    """Campground facility from the RIDB metadata API."""

    facility_id: str = Field(alias="FacilityID")
    facility_name: str = Field(alias="FacilityName")
    facility_type_description: str = Field("", alias="FacilityTypeDescription")
    latitude: float = Field(0.0, alias="FacilityLatitude")
    longitude: float = Field(0.0, alias="FacilityLongitude")
    parent_org_id: str = Field("", alias="ParentOrgID")
    parent_rec_area_id: str = Field("", alias="ParentRecAreaID")
    description: str = Field("", alias="FacilityDescription")
    reservable: bool = Field(False, alias="Reservable")
    enabled: bool = Field(True, alias="Enabled")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Registry (local enriched data)
# ---------------------------------------------------------------------------


class BookingSystem(StrEnum):
    RECGOV = "recgov"
    WA_STATE = "wa_state"  # GoingToCamp
    OR_STATE = "or_state"  # ReserveAmerica
    ID_STATE = "id_state"  # ReserveAmerica
    FCFS = "fcfs"  # First-come-first-served, no online system


class Campground(BaseModel):
    """A campground in the local registry, enriched beyond API metadata."""

    id: int | None = None  # SQLite rowid
    facility_id: str  # booking system ID (e.g. rec.gov facility_id)
    name: str
    booking_system: BookingSystem
    latitude: float = 0.0
    longitude: float = 0.0
    region: str = ""  # e.g. "Mt. Rainier NP", "Olympic NF"
    state: str = ""  # WA, OR, ID
    drive_minutes_from_base: int | None = None  # from Seattle, WA
    tags: list[str] = Field(default_factory=list)  # lakeside, river, kid-friendly, etc.
    booking_url_slug: str = ""  # URL slug for booking systems (e.g. RA)
    vibe: str = ""  # One-sentence campground character description
    notes: str = ""  # personal notes
    rating: int | None = None  # 1-5 personal rating
    total_sites: int | None = None
    enabled: bool = True  # include in searches
    created_at: datetime | None = None
    updated_at: datetime | None = None
