"""Watch CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from pnw_campsites.monitor.db import Watch
from pnw_campsites.routes.deps import (
    SESSION_COOKIE,
    get_current_user,
    get_registry,
    get_session_token,
    get_watch_db,
)

router = APIRouter(prefix="/api/watches", tags=["watches"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class WatchRequest(BaseModel):
    facility_id: str = Field(max_length=30, pattern=r"^[-\w]{1,30}$")
    name: str = Field(default="", max_length=200)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    min_nights: int = Field(default=1, ge=1, le=30)
    days_of_week: list[int] | None = None
    notify_topic: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    notification_channel: str = Field(
        default="", max_length=20, pattern=r"^(ntfy|pushover|web_push|)?$"
    )


class WatchResponse(BaseModel):
    id: int
    facility_id: str
    name: str
    start_date: str
    end_date: str
    min_nights: int
    days_of_week: list[int] | None
    notify_topic: str
    notification_channel: str
    enabled: bool
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owns_watch(watch: Watch, user_id: int | None, session_token: str) -> bool:
    """Check if the current user/session owns a watch."""
    return (
        (bool(user_id) and watch.user_id == user_id)
        or (bool(session_token) and watch.session_token == session_token)
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=WatchResponse)
async def create_watch(body: WatchRequest, request: Request, response: Response):
    db = get_watch_db()
    registry = get_registry()
    user_id = get_current_user(request)
    token = get_session_token(request, response) if not user_id else ""

    # Look up name from registry if not provided
    name = body.name
    if not name:
        cg = registry.get_by_facility_id(body.facility_id)
        name = cg.name if cg else f"Facility {body.facility_id}"

    watch = Watch(
        facility_id=body.facility_id,
        name=name,
        start_date=body.start_date,
        end_date=body.end_date,
        min_nights=body.min_nights,
        days_of_week=body.days_of_week,
        notify_topic=body.notify_topic,
        notification_channel=body.notification_channel,
        session_token=token,
        user_id=user_id,
    )
    if db.has_duplicate_watch(watch):
        raise HTTPException(
            status_code=409, detail="Watch already exists",
        )
    saved = db.add_watch(watch)
    return WatchResponse(
        id=saved.id,
        facility_id=saved.facility_id,
        name=saved.name,
        start_date=saved.start_date,
        end_date=saved.end_date,
        min_nights=saved.min_nights,
        days_of_week=saved.days_of_week,
        notify_topic=saved.notify_topic,
        notification_channel=saved.notification_channel,
        enabled=saved.enabled,
        created_at=saved.created_at,
    )


@router.get("", response_model=list[WatchResponse])
async def list_watches(request: Request, response: Response):
    db = get_watch_db()
    user_id = get_current_user(request)
    if user_id:
        watches = db.list_watches_by_user(user_id)
    else:
        token = get_session_token(request, response)
        watches = db.list_watches_by_session(token)
    return [
        WatchResponse(
            id=w.id,
            facility_id=w.facility_id,
            name=w.name,
            start_date=w.start_date,
            end_date=w.end_date,
            min_nights=w.min_nights,
            days_of_week=w.days_of_week,
            notify_topic=w.notify_topic,
            notification_channel=w.notification_channel,
            enabled=w.enabled,
            created_at=w.created_at,
        )
        for w in watches
    ]


@router.delete("/{watch_id}")
async def delete_watch(watch_id: int, request: Request, response: Response):
    db = get_watch_db()
    user_id = get_current_user(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    watch = db.get_watch(watch_id)
    if not watch or not _owns_watch(watch, user_id, token):
        return {"ok": False, "error": "Not found"}
    db.remove_watch(watch_id)
    return {"ok": True}


@router.patch("/{watch_id}/toggle")
async def toggle_watch(watch_id: int, request: Request, response: Response):
    db = get_watch_db()
    user_id = get_current_user(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    watch = db.get_watch(watch_id)
    if not watch or not _owns_watch(watch, user_id, token):
        return {"ok": False, "error": "Not found"}
    new_state = db.toggle_enabled(watch_id, token)
    return {"ok": True, "enabled": new_state}
