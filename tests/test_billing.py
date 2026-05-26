"""Tests for v1.4 billing foundation.

Covers:
- Schema migration adds the four user billing columns + two new tables
- WatchDB helpers (get_user_by_stripe_customer_id, stripe_event idempotency,
  subscription audit trail)
- billing.handle_webhook_event dispatch + idempotency
- billing entitlement helpers (is_pro, watch_limit, planner_session_limit)

Stripe SDK calls (checkout/portal session creation, signature verification)
are integration concerns deferred to slice 2/3 — this slice exercises only
pure logic that runs without network and without a real Stripe key.
"""

from __future__ import annotations

import json

import pytest

from pnw_campsites import billing
from pnw_campsites.monitor.db import User, WatchDB

# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


class TestSchema:
    def test_users_table_has_billing_columns(self, watch_db: WatchDB) -> None:
        cols = {
            r[1] for r in watch_db._conn.execute("PRAGMA table_info(users)")
        }
        assert "subscription_status" in cols
        assert "stripe_customer_id" in cols
        assert "subscription_id" in cols
        assert "subscription_expires_at" in cols

    def test_stripe_events_table_exists_with_unique_event_id(
        self, watch_db: WatchDB,
    ) -> None:
        cols = {
            r[1]
            for r in watch_db._conn.execute("PRAGMA table_info(stripe_events)")
        }
        assert {"event_id", "event_type", "payload", "processed_at"} <= cols

    def test_subscription_events_table_exists(self, watch_db: WatchDB) -> None:
        cols = {
            r[1]
            for r in watch_db._conn.execute(
                "PRAGMA table_info(subscription_events)"
            )
        }
        assert {
            "user_id", "event_type", "old_status", "new_status",
            "source", "occurred_at",
        } <= cols

    def test_new_user_defaults_to_free(self, watch_db: WatchDB) -> None:
        user = watch_db.create_user(
            User(email="free@example.com", supabase_id="sub-free")
        )
        retrieved = watch_db.get_user_by_id(user.id)
        assert retrieved is not None
        assert retrieved.subscription_status == "free"
        assert retrieved.stripe_customer_id == ""
        assert retrieved.subscription_id == ""


# ---------------------------------------------------------------------------
# WatchDB billing helpers
# ---------------------------------------------------------------------------


class TestBillingHelpers:
    def test_update_user_persists_billing_fields(
        self, watch_db: WatchDB,
    ) -> None:
        user = watch_db.create_user(
            User(email="paid@example.com", supabase_id="sub-paid")
        )
        watch_db.update_user(
            user.id,
            subscription_status="pro",
            stripe_customer_id="cus_test_123",
            subscription_id="sub_test_456",
        )
        retrieved = watch_db.get_user_by_id(user.id)
        assert retrieved.subscription_status == "pro"
        assert retrieved.stripe_customer_id == "cus_test_123"
        assert retrieved.subscription_id == "sub_test_456"

    def test_get_user_by_stripe_customer_id(self, watch_db: WatchDB) -> None:
        user = watch_db.create_user(
            User(email="cust@example.com", supabase_id="sub-cust")
        )
        watch_db.update_user(user.id, stripe_customer_id="cus_lookup")
        found = watch_db.get_user_by_stripe_customer_id("cus_lookup")
        assert found is not None
        assert found.id == user.id

    def test_get_user_by_stripe_customer_id_empty_returns_none(
        self, watch_db: WatchDB,
    ) -> None:
        # Defensive: don't return a user just because they have no customer id
        watch_db.create_user(
            User(email="nocust@example.com", supabase_id="sub-nocust")
        )
        assert watch_db.get_user_by_stripe_customer_id("") is None

    def test_stripe_event_idempotency(self, watch_db: WatchDB) -> None:
        assert watch_db.has_stripe_event("evt_001") is False
        watch_db.save_stripe_event("evt_001", "checkout.session.completed", "{}")
        assert watch_db.has_stripe_event("evt_001") is True

    def test_save_stripe_event_is_idempotent_under_replay(
        self, watch_db: WatchDB,
    ) -> None:
        # Same event_id arriving twice must not raise — INSERT OR IGNORE
        watch_db.save_stripe_event("evt_dup", "test.event", "{}")
        watch_db.save_stripe_event("evt_dup", "test.event", "{}")
        rows = watch_db._conn.execute(
            "SELECT COUNT(*) FROM stripe_events WHERE event_id=?",
            ("evt_dup",),
        ).fetchone()
        assert rows[0] == 1

    def test_log_subscription_event_creates_audit_row(
        self, watch_db: WatchDB,
    ) -> None:
        user = watch_db.create_user(
            User(email="audit@example.com", supabase_id="sub-audit")
        )
        watch_db.log_subscription_event(
            user_id=user.id,
            event_type="checkout.session.completed",
            old_status="free",
            new_status="pro",
        )
        events = watch_db.list_subscription_events(user.id)
        assert len(events) == 1
        assert events[0]["event_type"] == "checkout.session.completed"
        assert events[0]["old_status"] == "free"
        assert events[0]["new_status"] == "pro"
        assert events[0]["source"] == "webhook"


# ---------------------------------------------------------------------------
# Webhook event dispatch
# ---------------------------------------------------------------------------


@pytest.fixture
def pro_user_with_customer(watch_db: WatchDB) -> User:
    """A free-tier user pre-linked to a Stripe customer (no Pro yet)."""
    user = watch_db.create_user(
        User(email="hooks@example.com", supabase_id="sub-hooks")
    )
    watch_db.update_user(user.id, stripe_customer_id="cus_hook_123")
    return watch_db.get_user_by_id(user.id)


class TestWebhookDispatch:
    def test_checkout_completed_activates_pro(
        self, watch_db: WatchDB,
    ) -> None:
        user = watch_db.create_user(
            User(email="checkout@example.com", supabase_id="sub-co")
        )
        event = {
            "id": "evt_checkout_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": str(user.id),
                    "customer": "cus_new",
                    "subscription": "sub_new",
                },
            },
        }
        billing.handle_webhook_event(event, watch_db)
        refreshed = watch_db.get_user_by_id(user.id)
        assert refreshed.subscription_status == "pro"
        assert refreshed.stripe_customer_id == "cus_new"
        assert refreshed.subscription_id == "sub_new"
        # Audit trail recorded
        audit = watch_db.list_subscription_events(user.id)
        assert any(
            e["event_type"] == "checkout.session.completed" for e in audit
        )

    def test_checkout_completed_unknown_user_is_safe(
        self, watch_db: WatchDB,
    ) -> None:
        # Real-world: a stale webhook for a deleted user. Should log + no-op.
        event = {
            "id": "evt_unknown",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "99999",
                    "customer": "cus_x",
                    "subscription": "sub_x",
                },
            },
        }
        # Must not raise
        assert billing.handle_webhook_event(event, watch_db) is True

    def test_subscription_deleted_downgrades_to_free(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        watch_db.update_user(
            pro_user_with_customer.id,
            subscription_status="pro",
            subscription_id="sub_active",
        )
        event = {
            "id": "evt_del_1",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_hook_123"}},
        }
        billing.handle_webhook_event(event, watch_db)
        refreshed = watch_db.get_user_by_id(pro_user_with_customer.id)
        assert refreshed.subscription_status == "free"
        assert refreshed.subscription_id == ""

    def test_subscription_updated_to_active_promotes_to_pro(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        # User currently free; Stripe says subscription is active.
        event = {
            "id": "evt_upd_1",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_hook_123",
                    "status": "active",
                },
            },
        }
        billing.handle_webhook_event(event, watch_db)
        assert (
            watch_db.get_user_by_id(pro_user_with_customer.id).subscription_status
            == "pro"
        )

    def test_subscription_updated_past_due_retains_pro_grace(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        watch_db.update_user(pro_user_with_customer.id, subscription_status="pro")
        event = {
            "id": "evt_pd_1",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_hook_123",
                    "status": "past_due",
                },
            },
        }
        billing.handle_webhook_event(event, watch_db)
        # Grace period: stay Pro while Stripe retries
        assert (
            watch_db.get_user_by_id(pro_user_with_customer.id).subscription_status
            == "pro"
        )
        # But the past_due is audited for analytics
        audit = watch_db.list_subscription_events(pro_user_with_customer.id)
        assert any(
            e["event_type"] == "customer.subscription.past_due" for e in audit
        )

    def test_subscription_updated_canceled_downgrades(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        watch_db.update_user(pro_user_with_customer.id, subscription_status="pro")
        event = {
            "id": "evt_can_1",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_hook_123",
                    "status": "canceled",
                    "current_period_end": 1735689600,  # 2025-01-01
                },
            },
        }
        billing.handle_webhook_event(event, watch_db)
        refreshed = watch_db.get_user_by_id(pro_user_with_customer.id)
        assert refreshed.subscription_status == "free"
        assert "2025" in refreshed.subscription_expires_at

    def test_payment_failed_does_not_change_status(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        watch_db.update_user(pro_user_with_customer.id, subscription_status="pro")
        event = {
            "id": "evt_pf_1",
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_hook_123"}},
        }
        billing.handle_webhook_event(event, watch_db)
        assert (
            watch_db.get_user_by_id(pro_user_with_customer.id).subscription_status
            == "pro"
        )
        # But the failure is audited
        audit = watch_db.list_subscription_events(pro_user_with_customer.id)
        assert any(
            e["event_type"] == "invoice.payment_failed" for e in audit
        )

    def test_duplicate_event_is_skipped(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        watch_db.update_user(pro_user_with_customer.id, subscription_status="free")
        event = {
            "id": "evt_dup_dispatch",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_hook_123",
                    "status": "active",
                },
            },
        }
        # First call upgrades to Pro
        billing.handle_webhook_event(event, watch_db)
        assert (
            watch_db.get_user_by_id(pro_user_with_customer.id).subscription_status
            == "pro"
        )
        # Manually downgrade to verify the second call is a no-op
        watch_db.update_user(pro_user_with_customer.id, subscription_status="free")
        billing.handle_webhook_event(event, watch_db)
        # Still free — duplicate was skipped before re-upgrading
        assert (
            watch_db.get_user_by_id(pro_user_with_customer.id).subscription_status
            == "free"
        )

    def test_event_recorded_in_stripe_events_table(
        self,
        watch_db: WatchDB,
        pro_user_with_customer: User,
    ) -> None:
        event = {
            "id": "evt_recorded",
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_hook_123"}},
        }
        billing.handle_webhook_event(event, watch_db)
        assert watch_db.has_stripe_event("evt_recorded") is True
        row = watch_db._conn.execute(
            "SELECT event_type, payload FROM stripe_events WHERE event_id=?",
            ("evt_recorded",),
        ).fetchone()
        assert row["event_type"] == "invoice.payment_failed"
        # Payload is the full event JSON for forensics
        parsed = json.loads(row["payload"])
        assert parsed["id"] == "evt_recorded"


# ---------------------------------------------------------------------------
# Entitlement helpers
# ---------------------------------------------------------------------------


class TestEntitlements:
    def test_is_pro_for_pro_user(self) -> None:
        user = User(subscription_status="pro")
        assert billing.is_pro(user) is True

    def test_is_pro_for_free_user(self) -> None:
        user = User(subscription_status="free")
        assert billing.is_pro(user) is False

    def test_is_pro_for_none(self) -> None:
        # Anonymous sessions never have entitlements
        assert billing.is_pro(None) is False

    def test_watch_limit_free(self) -> None:
        assert billing.watch_limit(User(subscription_status="free")) == 3

    def test_watch_limit_pro_unlimited(self) -> None:
        # None == unlimited (callers must check for None, not >0)
        assert billing.watch_limit(User(subscription_status="pro")) is None

    def test_watch_limit_anonymous(self) -> None:
        # Anonymous users get the free-tier limit
        assert billing.watch_limit(None) == 3

    def test_planner_session_limits(self) -> None:
        assert (
            billing.planner_session_limit(User(subscription_status="free")) == 3
        )
        assert (
            billing.planner_session_limit(User(subscription_status="pro")) == 20
        )


# ---------------------------------------------------------------------------
# Configuration sanity
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_is_configured_false_without_keys(self, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        assert billing.is_configured() is False

    def test_is_configured_true_with_both_keys(self, monkeypatch) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        assert billing.is_configured() is True

    def test_get_client_raises_without_secret(self, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
            billing._get_client()

    def test_verify_webhook_raises_without_secret(self, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
            billing.verify_webhook(b"{}", "sig")

    def test_create_portal_session_requires_customer_id(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        with pytest.raises(ValueError, match="customer_id required"):
            billing.create_portal_session("")
