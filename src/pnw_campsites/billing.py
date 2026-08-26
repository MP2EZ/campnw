"""Stripe billing integration for Campable Pro subscriptions.

Configuration is environment-driven so this module is harmless when
`STRIPE_SECRET_KEY` is unset (dev/local). All public functions raise a
clear RuntimeError if called without credentials.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from stripe import RequestsClient, SignatureVerificationError, StripeClient, Webhook

from pnw_campsites.monitor.db import User, WatchDB
from pnw_campsites.posthog_client import capture_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env-driven; placeholders are safe for dev)
# ---------------------------------------------------------------------------

STRIPE_PRO_PRICE_ID_DEFAULT = "price_placeholder_pro_monthly"
SUCCESS_URL_DEFAULT = "https://campable.co/?billing=success"
CANCEL_URL_DEFAULT = "https://campable.co/pricing"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


# stripe-python's default socket timeout is 80s. A hung Stripe connection on a
# single-worker uvicorn therefore freezes the whole app for 80s (160s for
# checkout, which makes two sequential calls). Cap it well below any sensible
# request budget.
_STRIPE_TIMEOUT_SECONDS = 10

_stripe_client: StripeClient | None = None
_stripe_client_key: str = ""


def _get_client() -> StripeClient:
    """Return a memoized StripeClient.

    The default RequestsClient keeps its requests.Session on a thread-local, so
    constructing a client per call meant a fresh TCP+TLS handshake to
    api.stripe.com on every checkout, portal, and health probe.
    """
    global _stripe_client, _stripe_client_key
    key = _env("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    if _stripe_client is None or _stripe_client_key != key:
        _stripe_client = StripeClient(
            key,
            http_client=RequestsClient(timeout=_STRIPE_TIMEOUT_SECONDS),
        )
        _stripe_client_key = key
    return _stripe_client


def pro_price_id() -> str:
    """Resolve the Stripe price id used for Pro checkout.

    Shared with the dependency health sweep so the probe validates the exact
    price that checkout will charge against.
    """
    return _env("STRIPE_PRO_PRICE_ID", STRIPE_PRO_PRICE_ID_DEFAULT)


def is_configured() -> bool:
    """Return True when Stripe credentials are present (used for /api/billing gating)."""
    return bool(_env("STRIPE_SECRET_KEY") and _env("STRIPE_WEBHOOK_SECRET"))


# ---------------------------------------------------------------------------
# Checkout & Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    user_id: int,
    email: str,
    customer_id: str = "",
) -> tuple[str, str]:
    """Create a Stripe Checkout Session for Pro subscription.

    Returns (checkout_url, customer_id). Reuses an existing Stripe customer
    when `customer_id` is provided; otherwise creates one tagged with the
    Campable user id in metadata for forensics.
    """
    client = _get_client()
    price_id = pro_price_id()
    success_url = _env("STRIPE_SUCCESS_URL", SUCCESS_URL_DEFAULT)
    cancel_url = _env("STRIPE_CANCEL_URL", CANCEL_URL_DEFAULT)

    if not customer_id:
        customer = client.v1.customers.create(
            params={
                "email": email,
                "metadata": {"campable_user_id": str(user_id)},
            },
        )
        customer_id = customer.id

    session = client.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": str(user_id),
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
        },
    )
    return session.url, customer_id


def create_portal_session(customer_id: str) -> str:
    """Create a Stripe Customer Portal session for an existing customer."""
    if not customer_id:
        raise ValueError("customer_id required for portal session")
    client = _get_client()
    return_url = _env("STRIPE_SUCCESS_URL", SUCCESS_URL_DEFAULT)
    session = client.v1.billing_portal.sessions.create(
        params={"customer": customer_id, "return_url": return_url},
    )
    return session.url


# ---------------------------------------------------------------------------
# Webhook handling
# ---------------------------------------------------------------------------


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify a Stripe webhook signature and return the parsed event.

    Raises ValueError on missing config or invalid signature.
    """
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    try:
        # Webhook.construct_event takes raw bytes — never decoded — so the
        # HMAC signature can be validated against exactly what Stripe sent.
        event = Webhook.construct_event(payload, sig_header, secret)
    except SignatureVerificationError as e:
        raise ValueError(f"Invalid webhook signature: {e}") from e
    return event


def handle_webhook_event(event: dict, watch_db: WatchDB) -> bool:
    """Process a verified Stripe webhook event idempotently.

    Returns True if the event was handled or already-seen. Idempotency is
    claimed atomically *before* the handler runs, so concurrent deliveries
    of the same event can never both dispatch — only the first caller sees
    rowcount=1 from the underlying INSERT OR IGNORE.

    Failure semantics: if the handler raises after we've claimed the
    event, the claim row remains and Stripe's retries will be skipped.
    Operators can reconcile by inspecting subscription_events for the
    affected user (the audit table only contains rows the handler
    actually wrote, so absence indicates partial-failure mid-handler).
    Manual remediation: `DELETE FROM stripe_events WHERE event_id=?` to
    re-enable Stripe's next retry.
    """
    event_id = event.get("id", "")
    event_type = event.get("type", "")

    # Atomic claim — dispatch only if this call won the insert race.
    claimed = watch_db.save_stripe_event(
        event_id, event_type, json.dumps(event),
    )
    if not claimed:
        logger.info("Skipping duplicate Stripe event %s", event_id)
        return True

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event, watch_db)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(event, watch_db)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(event, watch_db)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(event, watch_db)
    else:
        logger.info("Ignoring Stripe event type: %s", event_type)

    return True


# ---------------------------------------------------------------------------
# Event handlers (private)
# ---------------------------------------------------------------------------


def _handle_checkout_completed(event: dict, watch_db: WatchDB) -> None:
    """Activate Pro on successful checkout."""
    session = event["data"]["object"]
    user_id_str = session.get("client_reference_id") or ""
    customer_id = session.get("customer", "") or ""
    subscription_id = session.get("subscription", "") or ""

    if not user_id_str:
        logger.warning(
            "checkout.session.completed missing client_reference_id (event=%s)",
            event.get("id"),
        )
        return

    user_id = int(user_id_str)
    user = watch_db.get_user_by_id(user_id)
    if user is None:
        logger.warning(
            "checkout.session.completed for unknown user %d (event=%s)",
            user_id, event.get("id"),
        )
        return

    old_status = user.subscription_status
    watch_db.update_user(
        user_id,
        subscription_status="pro",
        stripe_customer_id=customer_id,
        subscription_id=subscription_id,
        subscription_expires_at="",
    )
    watch_db.log_subscription_event(
        user_id=user_id,
        event_type="checkout.session.completed",
        old_status=old_status,
        new_status="pro",
        source="webhook",
    )
    # The purchase is only observable here. A client-side event would be lost
    # to adblockers, to the user closing the tab before Stripe redirects back,
    # and entirely to the native iOS flow (which upgrades in the system
    # browser). client_reference_id is str(user.id), which is the same
    # distinct_id the browser identifies with — so these join.
    capture_event(
        distinct_id=str(user_id),
        event="subscription_started",
        properties={
            "plan": "pro",
            "previous_status": old_status,
            "amount_cents": session.get("amount_total") or 0,
            "currency": session.get("currency") or "usd",
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "source": "webhook",
        },
        set_properties={"plan": "pro", "subscription_status": "pro"},
    )
    logger.info(
        "Activated Pro for user %d (customer=%s, subscription=%s)",
        user_id, customer_id, subscription_id,
    )


def _handle_subscription_updated(event: dict, watch_db: WatchDB) -> None:
    """Sync subscription status changes.

    Stripe's lifecycle for a cancel-at-period-end flow:
      1. User clicks cancel (portal) → fires updated with status=active +
         cancel_at_period_end=true. We keep Pro and record expires_at so
         the UI can show "Pro until {date}".
      2. Period ends → fires updated with status=canceled AND deleted.
         Either event downgrades.
    Immediate cancellations (admin/refund) skip step 1 and fire status=
    canceled directly. Either way, status=canceled is authoritative for
    "no longer entitled."
    """
    subscription = event["data"]["object"]
    customer_id = subscription.get("customer", "") or ""
    stripe_status = subscription.get("status", "")
    cancel_at_period_end = bool(subscription.get("cancel_at_period_end"))
    period_end_iso = _iso_from_epoch(_current_period_end(subscription))

    user = watch_db.get_user_by_stripe_customer_id(customer_id)
    if user is None:
        logger.warning(
            "customer.subscription.updated for unknown customer %s", customer_id,
        )
        return

    old_status = user.subscription_status
    old_expires_at = user.subscription_expires_at

    if stripe_status in ("active", "trialing"):
        # User is entitled to Pro. expires_at tracks scheduled cancel.
        new_expires_at = period_end_iso if cancel_at_period_end else ""
        watch_db.update_user(
            user.id,
            subscription_status="pro",
            subscription_expires_at=new_expires_at,
        )
        if old_status != "pro":
            watch_db.log_subscription_event(
                user_id=user.id,
                event_type="customer.subscription.updated",
                old_status=old_status,
                new_status="pro",
            )
        elif cancel_at_period_end and not old_expires_at:
            # User just scheduled a cancellation — record for analytics
            watch_db.log_subscription_event(
                user_id=user.id,
                event_type="customer.subscription.scheduled_cancel",
                old_status=old_status,
                new_status=old_status,
            )
            logger.info(
                "User %d scheduled cancel; Pro retained until %s",
                user.id, period_end_iso,
            )
        elif not cancel_at_period_end and old_expires_at:
            # User reversed their cancellation via portal
            watch_db.log_subscription_event(
                user_id=user.id,
                event_type="customer.subscription.uncanceled",
                old_status=old_status,
                new_status=old_status,
            )
            logger.info("User %d uncanceled; Pro continues indefinitely", user.id)
    elif stripe_status == "past_due":
        # Grace period during Stripe's payment retry window. Keep Pro.
        watch_db.log_subscription_event(
            user_id=user.id,
            event_type="customer.subscription.past_due",
            old_status=old_status,
            new_status=old_status,
        )
        logger.info("User %d subscription past_due (Pro retained)", user.id)
    elif stripe_status in ("canceled", "unpaid"):
        # Subscription has ended (period expired OR immediate cancel OR
        # retries exhausted). Downgrade now; clear expires_at because
        # entitlement has ended.
        watch_db.update_user(
            user.id,
            subscription_status="free",
            subscription_expires_at="",
        )
        watch_db.log_subscription_event(
            user_id=user.id,
            event_type="customer.subscription.updated",
            old_status=old_status,
            new_status="free",
        )
        logger.info(
            "User %d downgraded to free (stripe_status=%s)",
            user.id, stripe_status,
        )
    elif stripe_status == "incomplete_expired":
        # Initial payment never completed — the user was never Pro in the
        # first place. No state change; just log for forensics.
        logger.info(
            "User %d subscription expired before activation (no-op)", user.id,
        )


def _handle_subscription_deleted(event: dict, watch_db: WatchDB) -> None:
    """Revert user to free tier when subscription is deleted in Stripe."""
    subscription = event["data"]["object"]
    customer_id = subscription.get("customer", "") or ""

    user = watch_db.get_user_by_stripe_customer_id(customer_id)
    if user is None:
        logger.warning(
            "customer.subscription.deleted for unknown customer %s", customer_id,
        )
        return

    old_status = user.subscription_status
    watch_db.update_user(
        user.id,
        subscription_status="free",
        subscription_id="",
    )
    watch_db.log_subscription_event(
        user_id=user.id,
        event_type="customer.subscription.deleted",
        old_status=old_status,
        new_status="free",
    )
    capture_event(
        distinct_id=str(user.id),
        event="subscription_cancelled",
        properties={
            "plan_from": old_status,
            "plan_to": "free",
            "stripe_customer_id": customer_id,
            "source": "webhook",
        },
        set_properties={"plan": "free", "subscription_status": "free"},
    )
    logger.info("User %d subscription deleted; reverted to free", user.id)


def _handle_payment_failed(event: dict, watch_db: WatchDB) -> None:
    """Record payment failure as an audit event. Pro access is unchanged
    until `customer.subscription.updated` transitions the status."""
    invoice = event.get("data", {}).get("object", {})
    customer_id = invoice.get("customer", "") or ""
    user = watch_db.get_user_by_stripe_customer_id(customer_id)
    if user is None:
        logger.warning(
            "invoice.payment_failed for unknown customer %s", customer_id,
        )
        return
    watch_db.log_subscription_event(
        user_id=user.id,
        event_type="invoice.payment_failed",
        old_status=user.subscription_status,
        new_status=user.subscription_status,
    )
    capture_event(
        distinct_id=str(user.id),
        event="payment_failed",
        properties={
            "plan": user.subscription_status,
            "attempt_count": invoice.get("attempt_count") or 0,
            "amount_cents": invoice.get("amount_due") or 0,
            "currency": invoice.get("currency") or "usd",
            "source": "webhook",
        },
    )
    logger.warning(
        "Payment failed for user %d (customer=%s)", user.id, customer_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_from_epoch(value: object) -> str:
    """Convert a Stripe epoch-seconds timestamp into an ISO-8601 UTC string."""
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    if isinstance(value, str):
        return value
    return ""


def _current_period_end(subscription: dict) -> object:
    """Read current_period_end from a Stripe subscription payload.

    Stripe moved this field from the subscription root to
    ``subscription.items.data[0].current_period_end`` in API versions
    around 2024-09 and later. Newer versions (e.g. 2026-03-25.dahlia,
    which the v1.4 event destination uses) no longer populate the
    root-level field at all. Older versions still populate the root,
    so we check both for forward-and-backward compatibility.

    Returns the epoch-seconds int when present, else None.
    """
    root = subscription.get("current_period_end")
    if root is not None:
        return root
    items = subscription.get("items") or {}
    data = items.get("data") if isinstance(items, dict) else None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("current_period_end")
    return None


# ---------------------------------------------------------------------------
# Entitlement helpers (consumed by routes/* — read-only over WatchDB)
# ---------------------------------------------------------------------------


def is_pro(user: User | None) -> bool:
    """Return True when the user has an active Pro subscription."""
    return bool(user and user.subscription_status == "pro")


# Free-tier limits. Pro is unlimited. These constants are the
# single source of truth for free-tier gating across the app.
FREE_WATCH_LIMIT = 3
FREE_PLANNER_SESSIONS_PER_MONTH = 3
PRO_PLANNER_SESSIONS_PER_MONTH = 20


def watch_limit(user: User | None) -> int | None:
    """Return the max number of active watches for a user, or None for unlimited."""
    return None if is_pro(user) else FREE_WATCH_LIMIT


def planner_session_limit(user: User | None) -> int:
    """Return the per-month trip-planner session limit."""
    if is_pro(user):
        return PRO_PLANNER_SESSIONS_PER_MONTH
    return FREE_PLANNER_SESSIONS_PER_MONTH
