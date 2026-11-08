"""Data models for the campground registry and availability data."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
    OPEN = "Open"  # FCFS / walk-in, or stay continuation (see continuation_dates)
    CLOSED = "Closed"  # seasonal closure


class SiteFit(BaseModel):
    """What a site takes, as far as the booking system says. None = unknown.

    `fits_rv` with `max_rv_ft` None means RVs fit, no upper length stated.
    """

    model_config = ConfigDict(frozen=True)

    fits_tent: bool | None = None
    fits_van: bool | None = None
    fits_rv: bool | None = None  # RV or trailer
    max_rv_ft: int | None = None
    hookups: bool | None = None  # electric (or more)
    walk_in: bool | None = None


class CampsiteAvailability(BaseModel):
    """Per-campsite availability from the rec.gov availability endpoint."""

    campsite_id: str
    site: str  # e.g. "D016"
    loop: str  # e.g. "A-F"
    campsite_type: str  # e.g. "STANDARD NONELECTRIC"
    type_of_use: str  # e.g. "Overnight"
    min_num_people: int  # can be 0
    max_num_people: int
    # False when max_num_people is a provider placeholder (unseeded WA, RA
    # without the attribute): party-size filtering treats it as unknown.
    max_people_known: bool = True
    availabilities: dict[str, AvailabilityStatus]  # ISO datetime str -> status
    fit: SiteFit | None = None  # set by WA enrichment and ReserveAmerica

    def available_dates(self) -> list[str]:
        """Return sorted list of dates with Available status."""
        return sorted(
            d for d, s in self.availabilities.items() if s == AvailabilityStatus.AVAILABLE
        )

    def continuation_dates(self) -> set[str]:
        """Open nights bookable only as the tail of a stay that arrives earlier.

        Rec.gov marks the nights just past a campground's arrival window Open
        until they're released, then NYR beyond. Kirk Creek on 2026-11-07:
        Reserved/Available to May 7, Open to May 19 (Reserved where a stay
        runs on), NYR from May 20. So an Open night is continuation when the
        site's later nights, skipping Open and Reserved, reach NYR. Open that
        doesn't run into NYR keeps its walk-up meaning (ReserveAmerica WALK_UP).
        """
        continuation: set[str] = set()
        reaches_nyr = False
        for day in sorted(self.availabilities, reverse=True):
            status = self.availabilities[day]
            if status == AvailabilityStatus.NYR:
                reaches_nyr = True
            elif status == AvailabilityStatus.OPEN:
                if reaches_nyr:
                    continuation.add(day)
            elif status != AvailabilityStatus.RESERVED:
                reaches_nyr = False
        return continuation

    @property
    def is_fcfs(self) -> bool:
        """True if this site is FCFS — not bookable online."""
        statuses = set(self.availabilities.values())
        if statuses & {AvailabilityStatus.AVAILABLE, AvailabilityStatus.RESERVED}:
            return False
        if AvailabilityStatus.NOT_RESERVABLE in statuses:
            return True
        if AvailabilityStatus.OPEN not in statuses:
            return False
        continuation = self.continuation_dates()
        return any(
            status == AvailabilityStatus.OPEN and day not in continuation
            for day, status in self.availabilities.items()
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

    @classmethod
    def _missing_(cls, value):
        # Accept dash-style aliases (e.g. "wa-state") in addition to the
        # canonical underscore form. Avoids a recurring footgun at API/CLI
        # boundaries where one style is used but the enum expects the other.
        if isinstance(value, str) and "-" in value:
            try:
                return cls(value.replace("-", "_"))
            except ValueError:
                pass
        return None


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
    slug: str = ""  # URL-safe slug for SEO pages (e.g. "deception-pass-state-park")
    booking_url_slug: str = ""  # URL slug for booking systems (e.g. RA)
    vibe: str = ""  # One-sentence campground character description
    elevator_pitch: str = ""  # One sentence for collapsed result card
    description_rewrite: str = ""  # 2-3 sentences for expanded view
    best_for: str = ""  # Label: "families", "backpackers", etc.
    booking_tips: str = ""  # JSON array of tips from availability history
    notes: str = ""  # personal notes
    rating: int | None = None  # 1-5 personal rating
    total_sites: int | None = None
    image_urls: list[str] = Field(default_factory=list)  # source-CDN photo URLs (v1.35)
    image_attribution: str = ""  # e.g. "Recreation.gov", "Oregon State Parks"
    image_verified_at: datetime | None = None
    enabled: bool = True  # include in searches
    created_at: datetime | None = None
    updated_at: datetime | None = None
