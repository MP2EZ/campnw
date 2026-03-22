"""FastAPI backend exposing the campsite search library as a REST API."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import SearchEngine, SearchQuery
from pnw_campsites.urls import (
    recgov_availability_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
)

# ---------------------------------------------------------------------------
# App state — initialized in lifespan
# ---------------------------------------------------------------------------

_registry: CampgroundRegistry | None = None
_recgov: RecGovClient | None = None
_goingtocamp: GoingToCampClient | None = None
_engine: SearchEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _recgov, _goingtocamp, _engine
    load_dotenv()

    _registry = CampgroundRegistry()
    api_key = os.getenv("RIDB_API_KEY")
    if api_key:
        _recgov = RecGovClient(ridb_api_key=api_key)
        await _recgov.__aenter__()

    _goingtocamp = GoingToCampClient()
    await _goingtocamp.__aenter__()

    _engine = SearchEngine(_registry, _recgov, _goingtocamp)

    yield

    if _recgov:
        await _recgov.__aexit__(None, None, None)
    if _goingtocamp:
        await _goingtocamp.__aexit__(None, None, None)
    if _registry:
        _registry.close()


logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PNW Campsites", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class WindowResponse(BaseModel):
    campsite_id: str
    site_name: str
    loop: str
    campsite_type: str
    start_date: str
    end_date: str
    nights: int
    max_people: int
    is_fcfs: bool = False
    booking_url: str | None = None


class CampgroundResultResponse(BaseModel):
    facility_id: str
    name: str
    state: str
    booking_system: str
    latitude: float
    longitude: float
    total_available_sites: int
    fcfs_sites: int
    tags: list[str] = []
    estimated_drive_minutes: int | None = None
    availability_url: str | None = None
    windows: list[WindowResponse]
    error: str | None = None


class SearchWarningResponse(BaseModel):
    kind: str
    count: int
    source: str
    message: str


WARNING_MESSAGES = {
    "rate_limited": (
        "Some results may be missing — recreation.gov is rate limiting."
        " Try a narrower search."
    ),
    "waf_blocked": "WA State Parks results unavailable — the booking site is blocking requests.",
    "unavailable": "Some campgrounds couldn't be checked due to a service issue.",
}


class SearchResponse(BaseModel):
    campgrounds_checked: int
    campgrounds_with_availability: int
    results: list[CampgroundResultResponse]
    warnings: list[SearchWarningResponse] = []


class CampgroundResponse(BaseModel):
    id: int | None
    facility_id: str
    name: str
    booking_system: str
    state: str
    region: str
    latitude: float
    longitude: float
    tags: list[str]
    drive_minutes_from_base: int | None
    notes: str
    rating: int | None
    total_sites: int | None
    enabled: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_availability_url(
    facility_id: str,
    booking_system: BookingSystem,
    start_date: date | None,
    end_date: date | None = None,
) -> str:
    if booking_system == BookingSystem.WA_STATE:
        return wa_state_availability_url(facility_id, start_date, end_date)
    return recgov_availability_url(facility_id, start_date)


def _build_booking_url(
    facility_id: str,
    campsite_id: str,
    booking_system: BookingSystem,
    start_date: date,
    end_date: date,
) -> str | None:
    if booking_system == BookingSystem.RECGOV:
        return recgov_campsite_booking_url(
            facility_id, campsite_id, start_date, end_date
        )
    return None


def _format_result(r, booking_system: BookingSystem) -> CampgroundResultResponse:
    cg = r.campground
    start = None
    end = None
    reservable = [w for w in r.available_windows if not w.is_fcfs]
    if reservable:
        start = date.fromisoformat(reservable[0].start_date)
        end = date.fromisoformat(reservable[-1].end_date)

    windows = []
    for w in r.available_windows:
        booking_url = None
        if not w.is_fcfs:
            booking_url = _build_booking_url(
                cg.facility_id,
                w.campsite_id,
                cg.booking_system,
                date.fromisoformat(w.start_date),
                date.fromisoformat(w.end_date),
            )
        windows.append(
            WindowResponse(
                campsite_id=w.campsite_id,
                site_name=w.site_name,
                loop=w.loop,
                campsite_type=w.campsite_type,
                start_date=w.start_date,
                end_date=w.end_date,
                nights=w.nights,
                max_people=w.max_people,
                is_fcfs=w.is_fcfs,
                booking_url=booking_url,
            )
        )

    return CampgroundResultResponse(
        facility_id=cg.facility_id,
        name=cg.name,
        state=cg.state,
        booking_system=cg.booking_system.value,
        latitude=cg.latitude,
        longitude=cg.longitude,
        total_available_sites=r.total_available_sites,
        fcfs_sites=r.fcfs_sites,
        tags=cg.tags,
        estimated_drive_minutes=r.estimated_drive_minutes,
        availability_url=_build_availability_url(
            cg.facility_id, cg.booking_system, start, end
        ) if start else None,
        windows=windows,
        error=r.error,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/search", response_model=SearchResponse)
async def search(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    state: str | None = Query(None, description="Filter by state: WA, OR, ID"),
    nights: int = Query(2, description="Minimum consecutive nights"),
    days_of_week: str | None = Query(
        None, description="Comma-separated day numbers (0=Mon..6=Sun)"
    ),
    tags: str | None = Query(None, description="Comma-separated tags"),
    max_drive: int | None = Query(None, description="Max drive minutes"),
    from_location: str | None = Query(
        None, alias="from",
        description="Origin: seattle, bellevue, portland, spokane, or address",
    ),
    name: str | None = Query(None, description="Campground name filter"),
    source: str | None = Query(None, description="recgov or wa_state"),
    no_groups: bool = Query(False, description="Exclude group sites"),
    include_fcfs: bool = Query(False, description="Include FCFS sites"),
    limit: int = Query(20, description="Max campgrounds to check"),
):
    days_set = (
        {int(d) for d in days_of_week.split(",")}
        if days_of_week
        else None
    )
    booking_system = BookingSystem(source) if source else None

    query = SearchQuery(
        state=state,
        start_date=start_date,
        end_date=end_date,
        min_consecutive_nights=nights,
        days_of_week=days_set,
        tags=tags.split(",") if tags else None,
        max_drive_minutes=max_drive,
        from_location=from_location,
        name_like=name,
        include_group_sites=not no_groups,
        include_fcfs=include_fcfs,
        max_campgrounds=limit,
        booking_system=booking_system,
    )

    results = await _engine.search(query)

    return SearchResponse(
        campgrounds_checked=results.campgrounds_checked,
        campgrounds_with_availability=results.campgrounds_with_availability,
        results=[
            _format_result(r, booking_system or BookingSystem.RECGOV)
            for r in results.results
        ],
        warnings=[
            SearchWarningResponse(
                kind=w.kind,
                count=w.count,
                source=w.source,
                message=WARNING_MESSAGES.get(w.kind, "Some campgrounds couldn't be checked."),
            )
            for w in results.warnings
        ],
    )


@app.get("/api/check/{facility_id}", response_model=CampgroundResultResponse)
async def check(
    facility_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    nights: int = Query(1),
    source: str | None = Query(None, description="recgov or wa_state"),
):
    booking_system = BookingSystem(source) if source else None
    result = await _engine.check_specific(
        facility_id=facility_id,
        start_date=start_date,
        end_date=end_date,
        min_nights=nights,
        booking_system=booking_system,
    )
    return _format_result(
        result, booking_system or BookingSystem.RECGOV
    )


@app.get("/api/campgrounds", response_model=list[CampgroundResponse])
async def list_campgrounds(
    state: str | None = Query(None),
    tags: str | None = Query(None),
    max_drive: int | None = Query(None),
    name: str | None = Query(None),
    source: str | None = Query(None),
):
    booking_system = BookingSystem(source) if source else None
    results = _registry.search(
        state=state,
        tags=tags.split(",") if tags else None,
        max_drive_minutes=max_drive,
        name_like=name,
        booking_system=booking_system,
    )
    return [
        CampgroundResponse(
            id=cg.id,
            facility_id=cg.facility_id,
            name=cg.name,
            booking_system=cg.booking_system.value,
            state=cg.state,
            region=cg.region,
            latitude=cg.latitude,
            longitude=cg.longitude,
            tags=cg.tags,
            drive_minutes_from_base=cg.drive_minutes_from_base,
            notes=cg.notes,
            rating=cg.rating,
            total_sites=cg.total_sites,
            enabled=cg.enabled,
        )
        for cg in results
    ]


# ---------------------------------------------------------------------------
# Static file serving (production — serves React build from /static)
# ---------------------------------------------------------------------------

# Serve React build in production. Check the Docker location (/app/static)
# first, then fall back to relative paths for local dev.
_static_candidates = [
    Path("/app/static"),
    Path(__file__).resolve().parents[3] / "static",
    Path(__file__).resolve().parents[2] / "static",
]
for _static_dir in _static_candidates:
    if _static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
        break
