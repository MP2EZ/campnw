"""Trip CRUD routes."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pnw_campsites.routes.deps import get_current_user, get_watch_db

router = APIRouter(prefix="/api/trips", tags=["trips"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateTripRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)
    notes: str = Field(default="", max_length=2000)


class UpdateTripRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    start_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)


class AddCampgroundRequest(BaseModel):
    facility_id: str = Field(..., max_length=30)
    source: str = Field(default="recgov", max_length=20)
    name: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_auth(request: Request) -> int:
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _trip_to_dict(trip, campgrounds=None) -> dict:
    d = {
        "id": trip.id,
        "name": trip.name,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "notes": trip.notes,
        "created_at": trip.created_at,
        "updated_at": trip.updated_at,
    }
    if campgrounds is not None:
        d["campgrounds"] = [
            {
                "id": cg.id,
                "facility_id": cg.facility_id,
                "source": cg.source,
                "name": cg.name,
                "sort_order": cg.sort_order,
                "notes": cg.notes,
                "added_at": cg.added_at,
            }
            for cg in campgrounds
        ]
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("")
async def create_trip(body: CreateTripRequest, request: Request):
    user_id = _require_auth(request)
    db = get_watch_db()
    try:
        trip = db.create_trip(
            user_id, body.name,
            start_date=body.start_date,
            end_date=body.end_date,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return _trip_to_dict(trip, campgrounds=[])


@router.get("")
async def list_trips(request: Request):
    user_id = _require_auth(request)
    db = get_watch_db()
    trips = db.list_trips_by_user(user_id)
    result = []
    for trip in trips:
        cgs = db.get_trip_campgrounds(trip.id)
        result.append({
            **_trip_to_dict(trip),
            "campground_count": len(cgs),
        })
    return result


@router.get("/{trip_id}")
async def get_trip(trip_id: int, request: Request):
    user_id = _require_auth(request)
    db = get_watch_db()
    trip = db.get_trip(trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    campgrounds = db.get_trip_campgrounds(trip_id)
    return _trip_to_dict(trip, campgrounds=campgrounds)


@router.patch("/{trip_id}")
async def update_trip(trip_id: int, body: UpdateTripRequest, request: Request):
    user_id = _require_auth(request)
    db = get_watch_db()
    trip = db.get_trip(trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    updates = body.model_dump(exclude_none=True)
    updated = db.update_trip(trip_id, **updates)
    campgrounds = db.get_trip_campgrounds(trip_id)
    return _trip_to_dict(updated, campgrounds=campgrounds)


@router.delete("/{trip_id}")
async def delete_trip(trip_id: int, request: Request):
    user_id = _require_auth(request)
    db = get_watch_db()
    trip = db.get_trip(trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete_trip(trip_id)
    return {"ok": True}


@router.post("/{trip_id}/campgrounds")
async def add_campground(
    trip_id: int, body: AddCampgroundRequest, request: Request,
):
    user_id = _require_auth(request)
    db = get_watch_db()
    trip = db.get_trip(trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    try:
        cg = db.add_campground_to_trip(
            trip_id, body.facility_id, body.source, body.name, body.notes,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="Campground already in trip",
        ) from None
    return {
        "id": cg.id,
        "facility_id": cg.facility_id,
        "source": cg.source,
        "name": cg.name,
        "sort_order": cg.sort_order,
        "notes": cg.notes,
        "added_at": cg.added_at,
    }


@router.delete("/{trip_id}/campgrounds/{facility_id}")
async def remove_campground(
    trip_id: int, facility_id: str, request: Request,
    source: str = "recgov",
):
    user_id = _require_auth(request)
    db = get_watch_db()
    trip = db.get_trip(trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    removed = db.remove_campground_from_trip(trip_id, facility_id, source)
    if not removed:
        raise HTTPException(
            status_code=404, detail="Campground not in trip",
        )
    return {"ok": True}
