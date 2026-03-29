"""Web push notification routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from pnw_campsites.routes.deps import (
    SESSION_COOKIE,
    get_current_user,
    get_watch_db,
)

router = APIRouter(prefix="/api/push", tags=["push"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=500)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=500)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for client-side push subscription setup."""
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    return {"public_key": key}


@router.post("/subscribe")
async def push_subscribe(body: PushSubscribeRequest, request: Request, response: Response):
    """Register a web push subscription for the current user or session."""
    db = get_watch_db()
    user_id = get_current_user(request)
    session_token = request.cookies.get(SESSION_COOKIE, "") if not user_id else ""
    db.save_push_subscription(
        user_id=user_id,
        session_token=session_token,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
    )
    return {"ok": True}


@router.delete("/subscribe")
async def push_unsubscribe(body: PushUnsubscribeRequest, request: Request):
    """Remove a web push subscription. Scoped to current user/session."""
    db = get_watch_db()
    user_id = get_current_user(request)
    session_token = request.cookies.get(SESSION_COOKIE, "") if not user_id else ""
    db.delete_push_subscription_scoped(
        body.endpoint, user_id=user_id, session_token=session_token,
    )
    return {"ok": True}
