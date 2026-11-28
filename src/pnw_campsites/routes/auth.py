"""Authentication routes — profile CRUD and data export.

Signup/login/logout are handled client-side by Supabase Auth.
This module provides profile management for the local SQLite user record,
which is auto-provisioned on first authenticated API call (see deps.py).
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from stripe import StripeError

from pnw_campsites.billing import cancel_customer_subscriptions
from pnw_campsites.monitor.db import User
from pnw_campsites.posthog_client import delete_person
from pnw_campsites.routes.deps import get_current_user, get_watch_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    home_base: str | None = Field(default=None, max_length=200)
    default_state: str | None = Field(default=None, max_length=2)
    default_nights: int | None = Field(default=None, ge=1, le=14)
    default_from: str | None = Field(default=None, max_length=200)
    recommendations_enabled: bool | None = None
    preferred_tags: list[str] | None = None
    onboarding_complete: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "home_base": user.home_base,
        "default_state": user.default_state,
        "default_nights": user.default_nights,
        "default_from": user.default_from,
        "recommendations_enabled": user.recommendations_enabled,
        "preferred_tags": user.preferred_tags or [],
        "onboarding_complete": user.onboarding_complete,
    }


async def _delete_supabase_user(supabase_id: str) -> None:
    """Delete the user from Supabase Auth via the admin API.

    Raises on failure so the caller doesn't report a deletion that didn't
    happen. A 404 means it's already gone. Skipped when Supabase isn't
    configured (local dev).
    """
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{url}/auth/v1/admin/users/{supabase_id}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
    if resp.status_code != 404:
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_me(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"user": _user_to_dict(user)}


@router.patch("/me")
async def update_me(body: UpdateProfileRequest, request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    user = db.update_user(user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": _user_to_dict(user)}


@router.delete("/me")
async def delete_me(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.get_user_by_id(user_id)

    # First, before anything is deleted: a deleted account must not keep
    # being charged, and if this fails the user can still sign in and retry.
    billing_cancelled = False
    if user and user.stripe_customer_id:
        try:
            # The Stripe SDK is synchronous; inline it would block the event
            # loop of the single worker for every Stripe round-trip.
            cancelled = await asyncio.to_thread(
                cancel_customer_subscriptions, user.stripe_customer_id,
            )
        except StripeError:
            log.error("Failed to cancel Stripe subscriptions for user %s", user_id, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail="Couldn't cancel your subscription. Please try again.",
            ) from None
        if cancelled:
            billing_cancelled = True
            log.info("Cancelled %d subscription(s) for deleted user %s", len(cancelled), user_id)

    if user and user.supabase_id:
        # Before the local delete: if the sign-in survived, the next login
        # would silently re-provision the account, so keep both and let the
        # user retry.
        try:
            await _delete_supabase_user(user.supabase_id)
        except httpx.HTTPError:
            log.error("Failed to delete Supabase user %s", user.supabase_id, exc_info=True)
            detail = "Couldn't delete your account. Please try again."
            if billing_cancelled:
                detail = (
                    "Your subscription is cancelled, but we couldn't delete your"
                    " account. Please try again."
                )
            raise HTTPException(status_code=502, detail=detail) from None

    db.delete_user(user_id)
    # Best-effort: the account is already gone, and an analytics outage must
    # not leave the user unable to delete it. Failures are logged.
    await delete_person(str(user_id))
    return {"ok": True}


@router.get("/export")
async def export_data(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = db.get_user_export(user_id)
    return data
