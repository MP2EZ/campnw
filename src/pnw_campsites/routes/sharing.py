"""Shared link routes — create and view shared watches/trips."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pnw_campsites.routes.deps import get_current_user, get_watch_db

router = APIRouter(tags=["sharing"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateShareRequest(BaseModel):
    watch_id: int | None = None
    trip_id: int | None = None


# ---------------------------------------------------------------------------
# Rate limiting — 10 views/hour per UUID
# ---------------------------------------------------------------------------

_share_view_counts: dict[str, tuple[str, int]] = {}  # uuid -> (hour_key, count)


def _check_share_rate_limit(uuid: str) -> bool:
    hour_key = datetime.now().strftime("%Y-%m-%dT%H")
    entry = _share_view_counts.get(uuid)
    if entry is None or entry[0] != hour_key:
        _share_view_counts[uuid] = (hour_key, 1)
        return True
    if entry[1] >= 10:
        return False
    _share_view_counts[uuid] = (hour_key, entry[1] + 1)
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/api/shares")
async def create_share(body: CreateShareRequest, request: Request):
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = get_watch_db()

    # Verify ownership
    if body.watch_id:
        watch = db.get_watch(body.watch_id)
        if not watch or watch.user_id != user_id:
            raise HTTPException(status_code=404, detail="Watch not found")
    elif body.trip_id:
        trip = db.get_trip(body.trip_id)
        if not trip or trip.user_id != user_id:
            raise HTTPException(status_code=404, detail="Trip not found")
    else:
        raise HTTPException(status_code=422, detail="Specify watch_id or trip_id")

    link = db.create_shared_link(
        user_id, watch_id=body.watch_id, trip_id=body.trip_id,
    )
    return {
        "uuid": link.uuid,
        "expires_at": link.expires_at,
    }


@router.get("/api/shared/{uuid}")
async def view_shared(uuid: str):
    """Public endpoint — no auth required."""
    if not _check_share_rate_limit(uuid):
        raise HTTPException(status_code=429, detail="Too many views")

    db = get_watch_db()
    link = db.get_shared_link(uuid)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Check expiry and revocation
    if link.revoked:
        raise HTTPException(status_code=410, detail="Link revoked")
    if link.expires_at < datetime.now().isoformat():
        raise HTTPException(status_code=410, detail="Link expired")

    result: dict = {"uuid": uuid, "type": None}

    if link.watch_id:
        watch = db.get_watch(link.watch_id)
        if watch:
            result["type"] = "watch"
            result["watch"] = {
                "name": watch.name,
                "facility_id": watch.facility_id,
                "start_date": watch.start_date,
                "end_date": watch.end_date,
                "min_nights": watch.min_nights,
            }

    if link.trip_id:
        trip = db.get_trip(link.trip_id)
        if trip:
            campgrounds = db.get_trip_campgrounds(link.trip_id)
            result["type"] = "trip"
            result["trip"] = {
                "name": trip.name,
                "start_date": trip.start_date,
                "end_date": trip.end_date,
                "campgrounds": [
                    {
                        "facility_id": cg.facility_id,
                        "source": cg.source,
                        "name": cg.name,
                    }
                    for cg in campgrounds
                ],
            }

    return result


@router.delete("/api/shares/{uuid}")
async def revoke_share(uuid: str, request: Request):
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = get_watch_db()
    if not db.revoke_shared_link(uuid, user_id):
        raise HTTPException(status_code=404, detail="Link not found")
    return {"ok": True}
