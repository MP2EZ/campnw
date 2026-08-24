"""Billing routes — Stripe Checkout, Customer Portal, webhooks, status.

Slice 2 of v1.4 monetization. Webhook endpoint authenticates via Stripe
signature only (no Bearer token); all other endpoints require a logged-in
Supabase user.

`/api/billing/checkout` and `/api/billing/portal` return a redirect URL
that the frontend opens in a top-level navigation — never embed in an
iframe (Stripe blocks framing for security).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pnw_campsites import billing
from pnw_campsites.routes.deps import (
    get_current_user_obj,
    get_watch_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class StatusResponse(BaseModel):
    subscription_status: str
    subscription_expires_at: str
    has_stripe_customer: bool
    is_pro: bool
    watch_limit: int | None
    planner_session_limit: int
    configured: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(request: Request) -> CheckoutResponse:
    """Start a Stripe Checkout Session and return the redirect URL.

    Requires authentication. Reuses the user's existing Stripe customer
    when one is linked; otherwise creates one tagged with the Campable
    user id for forensics.
    """
    if not billing.is_configured():
        raise HTTPException(
            status_code=503, detail="Billing is not configured",
        )

    user = get_current_user_obj(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    if billing.is_pro(user):
        # Refusing here avoids accidentally creating a second active
        # subscription for the same user (which Stripe will happily allow).
        raise HTTPException(
            status_code=409,
            detail="Already on Pro — manage via /api/billing/portal",
        )

    try:
        # The Stripe SDK is synchronous. Called inline from an async handler on
        # a single uvicorn worker it blocks the event loop for the whole
        # round-trip — every other user's search and the poller included.
        url, customer_id = await asyncio.to_thread(
            billing.create_checkout_session,
            user_id=user.id,
            email=user.email,
            customer_id=user.stripe_customer_id,
        )
    except Exception as e:
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(
            status_code=502, detail="Stripe checkout unavailable",
        ) from e

    # Persist the Stripe customer id even before checkout completes — the
    # webhook handler relies on this for `customer.subscription.*` events
    # that arrive on the same customer.
    if customer_id and customer_id != user.stripe_customer_id:
        get_watch_db().update_user(user.id, stripe_customer_id=customer_id)

    return CheckoutResponse(url=url)


@router.post("/portal", response_model=PortalResponse)
async def open_portal(request: Request) -> PortalResponse:
    """Open the Stripe Customer Portal for the current user.

    Requires authentication and a previously-linked Stripe customer (set
    when the user first ran checkout). Free users without a customer get
    a 409 — there's nothing to manage.
    """
    if not billing.is_configured():
        raise HTTPException(
            status_code=503, detail="Billing is not configured",
        )

    user = get_current_user_obj(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=409,
            detail="No Stripe customer on file — use /checkout first",
        )

    try:
        url = await asyncio.to_thread(
            billing.create_portal_session, user.stripe_customer_id,
        )
    except Exception as e:
        logger.exception("Stripe portal session creation failed")
        raise HTTPException(
            status_code=502, detail="Stripe portal unavailable",
        ) from e

    return PortalResponse(url=url)


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Receive a Stripe webhook delivery.

    Authentication is via Stripe signature only — no Bearer token. The
    signature is HMAC-SHA256 over the raw request bytes, validated
    against STRIPE_WEBHOOK_SECRET. Returns 400 for any signature failure
    so Stripe retries with the same payload.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = billing.verify_webhook(payload, sig_header)
    except ValueError as e:
        # 400 (not 401) is what Stripe documents: retries on 4xx-except-400
        # are not exponentially backed off the same way, so a 400 keeps
        # the retry rhythm steady.
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(
            status_code=400, detail=str(e),
        ) from e

    try:
        billing.handle_webhook_event(event, get_watch_db())
    except Exception:
        # Handler crashed mid-flight — log loudly and return 500 so Stripe
        # retries. Note: the claim row in stripe_events may already be
        # present (see billing.handle_webhook_event docstring for the
        # operator runbook on partial-failure remediation).
        logger.exception(
            "Webhook handler crashed for event id=%s type=%s",
            event.get("id"), event.get("type"),
        )
        raise HTTPException(
            status_code=500, detail="Handler error",
        ) from None

    return {"ok": True}


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    """Return the current user's subscription state + entitlements.

    Anonymous users get the free-tier entitlement shape — no Pro, free
    watch/planner limits. UI uses this both to render the billing
    settings page and to gate Pro features client-side.
    """
    user = get_current_user_obj(request)
    return StatusResponse(
        subscription_status=user.subscription_status if user else "free",
        subscription_expires_at=user.subscription_expires_at if user else "",
        has_stripe_customer=bool(user and user.stripe_customer_id),
        is_pro=billing.is_pro(user),
        watch_limit=billing.watch_limit(user),
        planner_session_limit=billing.planner_session_limit(user),
        configured=billing.is_configured(),
    )
