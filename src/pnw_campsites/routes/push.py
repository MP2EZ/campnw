"""Web push notification routes."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pnw_campsites.monitor.notify import is_push_service_endpoint
from pnw_campsites.routes.deps import (
    SESSION_COOKIE,
    check_ip_quota,
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

    @field_validator("endpoint")
    @classmethod
    def _push_service_only(cls, v: str) -> str:
        if not is_push_service_endpoint(v):
            raise ValueError("endpoint must be a browser push service URL")
        return v


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=500)


# APNs device tokens are hex. iOS hands out 32 bytes today; Apple says the
# length may change, so allow up to 100 bytes.
_DEVICE_TOKEN = r"^[0-9a-f]{64,200}$"


class DeviceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(pattern=_DEVICE_TOKEN)
    platform: Literal["ios"]

    @field_validator("token", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v


class DeviceTokenDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(pattern=_DEVICE_TOKEN)

    @field_validator("token", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for client-side push subscription setup."""
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    return {"public_key": key}


@router.post("/subscribe")
async def push_subscribe(body: PushSubscribeRequest, request: Request):
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


# Registrations per user per day. A phone registers on launch and sign-in;
# this only stops a script filling the table with junk tokens.
_DEVICE_TOKEN_DAILY_LIMIT = 30
_device_token_registrations: dict[str, tuple[str, int]] = {}


@router.post("/device-token")
async def register_device_token(body: DeviceTokenRequest, request: Request):
    """Register this phone's APNs token for the signed-in user. Anonymous
    sessions can't: the app only offers alerts after sign-in. The response
    is the same whether the token was new or moved from another account."""
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not check_ip_quota(
        _device_token_registrations, str(user_id), _DEVICE_TOKEN_DAILY_LIMIT,
    ):
        raise HTTPException(status_code=429, detail="Too many registrations today")
    get_watch_db().save_device_token(user_id, body.token, body.platform)
    return {"ok": True}


@router.delete("/device-token")
async def delete_device_token(body: DeviceTokenDeleteRequest):
    """Stop this phone receiving alerts (called before sign-out). Holding the
    token is the proof, so an expired session can still clear a shared
    phone."""
    get_watch_db().delete_device_token(body.token)
    return {"ok": True}
