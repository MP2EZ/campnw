"""Poll status route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pnw_campsites.routes.deps import (
    get_current_user,
    get_poll_state,
    get_watch_db,
)

router = APIRouter(prefix="/api", tags=["poll"])


@router.get("/poll-status")
async def poll_status(request: Request):
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = get_watch_db()
    poll_state = get_poll_state()
    recent = db.get_recent_notifications(limit=10) if db else []
    return {
        **poll_state,
        "recent_notifications": recent,
    }
