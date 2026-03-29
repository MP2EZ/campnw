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
    facility_id: str = Field(default="", max_length=30, pattern=r"^[-\w]{0,30}$")
    name: str = Field(default="", max_length=200)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    min_nights: int = Field(default=1, ge=1, le=30)
    days_of_week: list[int] | None = None
    notify_topic: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    notification_channel: str = Field(
        default="", max_length=20, pattern=r"^(ntfy|pushover|web_push|)?$"
    )
    watch_type: str = Field(default="single", pattern=r"^(single|template)$")
    search_params: dict | None = None


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
    watch_type: str = "single"
    search_params: dict | None = None


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
    import json as _json

    db = get_watch_db()
    registry = get_registry()
    user_id = get_current_user(request)
    token = get_session_token(request, response) if not user_id else ""

    # Validate: template needs search_params, single needs facility_id
    if body.watch_type == "template":
        if not body.search_params:
            raise HTTPException(
                status_code=422,
                detail="Template watches require search_params",
            )
    elif not body.facility_id:
        raise HTTPException(
            status_code=422,
            detail="Single watches require facility_id",
        )

    # Look up name from registry if not provided
    name = body.name
    if not name and body.facility_id:
        cg = registry.get_by_facility_id(body.facility_id)
        name = cg.name if cg else f"Facility {body.facility_id}"
    if not name and body.watch_type == "template":
        name = "Search pattern watch"

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
        watch_type=body.watch_type,
        search_params=_json.dumps(body.search_params) if body.search_params else "",
    )
    if body.watch_type == "single" and db.has_duplicate_watch(watch):
        raise HTTPException(
            status_code=409, detail="Watch already exists",
        )
    saved = db.add_watch(watch)
    return _watch_to_response(saved)


def _watch_to_response(w: Watch) -> WatchResponse:
    import json as _json
    return WatchResponse(
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
        watch_type=w.watch_type,
        search_params=_json.loads(w.search_params) if w.search_params else None,
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
    return [_watch_to_response(w) for w in watches]


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
