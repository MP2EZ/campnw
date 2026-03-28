"""Stripe billing integration for campnw Pro subscriptions."""

from __future__ import annotations

import logging
import os

from stripe import SignatureVerificationError, StripeClient, Webhook

from pnw_campsites.monitor.db import WatchDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all placeholder defaults until Stripe account is set up)
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.getenv(
    "STRIPE_PRO_PRICE_ID", "price_placeholder_pro_monthly",
)
STRIPE_SUCCESS_URL = os.getenv(
    "STRIPE_SUCCESS_URL",
    "https://campnw.palouselabs.com/?billing=success",
)
STRIPE_CANCEL_URL = os.getenv(
    "STRIPE_CANCEL_URL",
    "https://campnw.palouselabs.com/pricing",
)


def _get_client() -> StripeClient:
    key = STRIPE_SECRET_KEY or os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    return StripeClient(key)


# ---------------------------------------------------------------------------
# Checkout & Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    user_id: int,
    email: str,
    customer_id: str | None = None,
) -> str:
    """Create a Stripe Checkout Session for Pro subscription.

    Returns the checkout URL to redirect the user to.
    """
    client = _get_client()

    # Create or reuse Stripe customer
    if not customer_id:
        customer = client.v1.customers.create(
            params={
                "email": email,
                "metadata": {"campnw_user_id": str(user_id)},
            },
        )
        customer_id = customer.id

    session = client.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": str(user_id),
            "line_items": [{"price": STRIPE_PRO_PRICE_ID, "quantity": 1}],
            "success_url": STRIPE_SUCCESS_URL,
            "cancel_url": STRIPE_CANCEL_URL,
        },
    )
    return session.url, customer_id


def create_portal_session(customer_id: str) -> str:
    """Create a Stripe Customer Portal session.

    Returns the portal URL for the user to manage billing.
    """
    client = _get_client()
    session = client.v1.billing_portal.sessions.create(
        params={
            "customer": customer_id,
            "return_url": STRIPE_SUCCESS_URL,
        },
    )
    return session.url


# ---------------------------------------------------------------------------
# Webhook handling
# ---------------------------------------------------------------------------


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature and return the event.

    Raises ValueError on invalid signature.
    """
    secret = STRIPE_WEBHOOK_SECRET or os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    try:
        event = Webhook.construct_event(payload, sig_header, secret)
    except SignatureVerificationError as e:
        raise ValueError(f"Invalid webhook signature: {e}") from e
    return event


def handle_webhook_event(event: dict, watch_db: WatchDB) -> bool:
    """Process a verified Stripe webhook event.

    Returns True if the event was processed (or already seen).
    """
    event_id = event.get("id", "")
    event_type = event.get("type", "")

    # Idempotency: skip if we've already processed this event
    if watch_db.has_stripe_event(event_id):
        logger.info("Skipping duplicate Stripe event %s", event_id)
        return True

    import json
    payload_str = json.dumps(event)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event, watch_db)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(event, watch_db)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(event, watch_db)
    elif event_type == "invoice.payment_failed":
        logger.warning(
            "Payment failed for customer %s",
            event.get("data", {}).get("object", {}).get("customer"),
        )
    else:
        logger.info("Ignoring Stripe event type: %s", event_type)

    # Record event for idempotency
    watch_db.save_stripe_event(event_id, event_type, payload_str)
    return True


def _handle_checkout_completed(event: dict, watch_db: WatchDB) -> None:
    """Handle checkout.session.completed — activate Pro subscription."""
    session = event["data"]["object"]
    user_id_str = session.get("client_reference_id")
    customer_id = session.get("customer", "")
    subscription_id = session.get("subscription", "")

    if not user_id_str:
        logger.warning("checkout.session.completed without client_reference_id")
        return

    user_id = int(user_id_str)
    logger.info(
        "Activating Pro for user %d (customer=%s, subscription=%s)",
        user_id, customer_id, subscription_id,
    )
    watch_db.update_user(
        user_id,
        subscription_status="pro",
        stripe_customer_id=customer_id,
        subscription_id=subscription_id,
    )


def _handle_subscription_updated(event: dict, watch_db: WatchDB) -> None:
    """Handle customer.subscription.updated — sync status."""
    subscription = event["data"]["object"]
    customer_id = subscription.get("customer", "")
    status = subscription.get("status", "")

    user = _find_user_by_customer_id(watch_db, customer_id)
    if not user:
        logger.warning(
            "subscription.updated for unknown customer %s", customer_id,
        )
        return

    if status in ("active", "trialing"):
        watch_db.update_user(user.id, subscription_status="pro")
    elif status in ("canceled", "unpaid", "past_due"):
        expires_at = subscription.get("current_period_end", "")
        if isinstance(expires_at, int):
            from datetime import datetime, timezone
            expires_at = datetime.fromtimestamp(
                expires_at, tz=timezone.utc,
            ).isoformat()
        watch_db.update_user(
            user.id,
            subscription_status="free",
            subscription_expires_at=expires_at,
        )
        logger.info("User %d downgraded to free (status=%s)", user.id, status)


def _handle_subscription_deleted(event: dict, watch_db: WatchDB) -> None:
    """Handle customer.subscription.deleted — revert to free."""
    subscription = event["data"]["object"]
    customer_id = subscription.get("customer", "")

    user = _find_user_by_customer_id(watch_db, customer_id)
    if not user:
        logger.warning(
            "subscription.deleted for unknown customer %s", customer_id,
        )
        return

    watch_db.update_user(
        user.id,
        subscription_status="free",
        subscription_id="",
    )
    logger.info("User %d subscription deleted, reverted to free", user.id)


def _find_user_by_customer_id(watch_db: WatchDB, customer_id: str):
    """Find a user by their Stripe customer ID."""
    if not customer_id:
        return None
    row = watch_db._conn.execute(
        "SELECT * FROM users WHERE stripe_customer_id=?",
        (customer_id,),
    ).fetchone()
    if row:
        return watch_db._row_to_user(row)
    return None
