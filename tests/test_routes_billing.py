"""Tests for v1.4 billing routes + watch limit enforcement.

Covers the HTTP surface added by slice 2 of v1.4 monetization:
- GET /api/billing/status (anonymous + authenticated, free + pro)
- POST /api/billing/checkout (configured/unconfigured, auth, already-pro)
- POST /api/billing/portal (configured/unconfigured, auth, no customer)
- POST /api/billing/webhook (bad signature, good signature + dispatch)
- POST /api/watches limit enforcement (HTTP 402, Pro bypass, anonymous cap)

Stripe SDK network calls (real Checkout / Portal session creation) are
mocked at the billing module boundary — we trust billing.create_*_session
to talk to Stripe, and verify the route hands off correctly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import signup_and_auth

# ---------------------------------------------------------------------------
# /api/billing/status
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_anonymous_gets_free_tier_shape(self, api_client) -> None:
        resp = api_client.get("/api/billing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_status"] == "free"
        assert data["is_pro"] is False
        assert data["watch_limit"] == 3
        assert data["planner_session_limit"] == 3
        assert data["has_stripe_customer"] is False

    def test_free_user_status(self, api_client) -> None:
        _, headers = signup_and_auth(api_client, email="free@example.com")
        resp = api_client.get("/api/billing/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_status"] == "free"
        assert data["is_pro"] is False
        assert data["watch_limit"] == 3

    def test_pro_user_status(self, api_client) -> None:
        user_data, headers = signup_and_auth(api_client, email="pro@example.com")
        # Manually upgrade to Pro via DB
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"],
            subscription_status="pro",
            stripe_customer_id="cus_test",
        )
        resp = api_client.get("/api/billing/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_status"] == "pro"
        assert data["is_pro"] is True
        # Pro users have no upper bound on watches
        assert data["watch_limit"] is None
        assert data["planner_session_limit"] == 20
        assert data["has_stripe_customer"] is True

    def test_configured_flag_reflects_env(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        resp = api_client.get("/api/billing/status")
        assert resp.json()["configured"] is True


# ---------------------------------------------------------------------------
# /api/billing/checkout
# ---------------------------------------------------------------------------


class TestCheckoutEndpoint:
    def test_unconfigured_returns_503(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        _, headers = signup_and_auth(api_client, email="x@example.com")
        resp = api_client.post("/api/billing/checkout", headers=headers)
        assert resp.status_code == 503

    def test_anonymous_returns_401(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        resp = api_client.post("/api/billing/checkout")
        assert resp.status_code == 401

    def test_already_pro_returns_409(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        user_data, headers = signup_and_auth(api_client, email="pro@example.com")
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], subscription_status="pro",
        )
        resp = api_client.post("/api/billing/checkout", headers=headers)
        assert resp.status_code == 409

    def test_successful_checkout_returns_url_and_persists_customer(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        user_data, headers = signup_and_auth(api_client, email="new@example.com")
        with patch(
            "pnw_campsites.billing.create_checkout_session",
            return_value=("https://checkout.stripe.com/abc", "cus_newcust"),
        ):
            resp = api_client.post("/api/billing/checkout", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://checkout.stripe.com/abc"
        # Customer id stored so subsequent webhook events resolve to the user
        import pnw_campsites.api as api_module
        refreshed = api_module._watch_db.get_user_by_id(user_data["id"])
        assert refreshed.stripe_customer_id == "cus_newcust"

    def test_stripe_failure_returns_502(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        _, headers = signup_and_auth(api_client, email="fail@example.com")
        with patch(
            "pnw_campsites.billing.create_checkout_session",
            side_effect=RuntimeError("Stripe is down"),
        ):
            resp = api_client.post("/api/billing/checkout", headers=headers)
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /api/billing/portal
# ---------------------------------------------------------------------------


class TestPortalEndpoint:
    def test_unconfigured_returns_503(self, api_client, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        _, headers = signup_and_auth(api_client, email="x@example.com")
        resp = api_client.post("/api/billing/portal", headers=headers)
        assert resp.status_code == 503

    def test_anonymous_returns_401(self, api_client, monkeypatch) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        resp = api_client.post("/api/billing/portal")
        assert resp.status_code == 401

    def test_no_customer_returns_409(self, api_client, monkeypatch) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        _, headers = signup_and_auth(api_client, email="nocust@example.com")
        resp = api_client.post("/api/billing/portal", headers=headers)
        assert resp.status_code == 409

    def test_returns_portal_url(self, api_client, monkeypatch) -> None:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        user_data, headers = signup_and_auth(
            api_client, email="portal@example.com",
        )
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], stripe_customer_id="cus_p",
        )
        with patch(
            "pnw_campsites.billing.create_portal_session",
            return_value="https://billing.stripe.com/xyz",
        ):
            resp = api_client.post("/api/billing/portal", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://billing.stripe.com/xyz"


# ---------------------------------------------------------------------------
# /api/billing/webhook
# ---------------------------------------------------------------------------


class TestWebhookEndpoint:
    def test_invalid_signature_returns_400(self, api_client) -> None:
        # No STRIPE_WEBHOOK_SECRET in env → verify_webhook raises ValueError
        resp = api_client.post(
            "/api/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=0,v1=garbage"},
        )
        assert resp.status_code == 400

    def test_valid_event_dispatches_handler(
        self, api_client, monkeypatch,
    ) -> None:
        # Mock signature verification to return a constructed event;
        # exercise the real dispatch path through billing.handle_webhook_event.
        user_data, headers = signup_and_auth(
            api_client, email="hook@example.com",
        )
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], stripe_customer_id="cus_webhook",
        )

        event = {
            "id": "evt_real_dispatch",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_webhook",
                    "status": "active",
                },
            },
        }
        with patch(
            "pnw_campsites.billing.verify_webhook", return_value=event,
        ):
            resp = api_client.post(
                "/api/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=0,v1=ignored"},
            )
        assert resp.status_code == 200
        # Dispatch effect: user promoted to Pro
        refreshed = api_module._watch_db.get_user_by_id(user_data["id"])
        assert refreshed.subscription_status == "pro"

    def test_handler_crash_returns_500(
        self, api_client, monkeypatch,
    ) -> None:
        # If handle_webhook_event raises (e.g., DB connection blip), the
        # route must surface 500 so Stripe retries.
        with patch(
            "pnw_campsites.billing.verify_webhook",
            return_value={"id": "evt_x", "type": "unknown"},
        ), patch(
            "pnw_campsites.billing.handle_webhook_event",
            side_effect=RuntimeError("db connection lost"),
        ):
            resp = api_client.post(
                "/api/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=0,v1=ignored"},
            )
        assert resp.status_code == 500

    def test_handler_crash_preserves_claim_row_for_operator_runbook(
        self, api_client, monkeypatch,
    ) -> None:
        # When a handler crashes AFTER save_stripe_event has claimed the
        # event_id, the claim row remains in stripe_events even though the
        # route returns 500. Stripe's retry will be skipped as a duplicate.
        # The operator runbook (documented in billing.handle_webhook_event)
        # requires DELETE FROM stripe_events WHERE event_id=? to re-enable
        # retry. This test locks in the claim-row preservation behaviour
        # so any future refactor that "fixes" it (e.g., by rolling back
        # the row on exception) breaks the runbook contract loudly.
        user_data, headers = signup_and_auth(
            api_client, email="crashtest@example.com",
        )
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], stripe_customer_id="cus_crash",
        )

        # Inject a real verify_webhook that returns a known event, and
        # break _handle_subscription_updated AFTER the claim row gets
        # written by handle_webhook_event.
        event = {
            "id": "evt_crash_runbook",
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": "cus_crash", "status": "active"},
            },
        }
        with patch(
            "pnw_campsites.billing.verify_webhook", return_value=event,
        ), patch(
            "pnw_campsites.billing._handle_subscription_updated",
            side_effect=RuntimeError("DB blip mid-handler"),
        ):
            resp = api_client.post(
                "/api/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=0,v1=ignored"},
            )
        assert resp.status_code == 500
        # Claim row was inserted before the handler ran → still present
        assert api_module._watch_db.has_stripe_event("evt_crash_runbook")


# ---------------------------------------------------------------------------
# Watch limit enforcement
# ---------------------------------------------------------------------------


def _post_watch(client, headers: dict | None = None, n: int = 1) -> list:
    """Create n watches sequentially; return the list of responses."""
    responses = []
    for i in range(n):
        body = {
            "facility_id": f"fac_{i}",
            "name": f"Watch {i}",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "min_nights": 1,
        }
        resp = client.post("/api/watches", json=body, headers=headers or {})
        responses.append(resp)
    return responses


class TestWatchLimitEnforcement:
    def test_free_user_can_create_three_watches(self, api_client) -> None:
        _, headers = signup_and_auth(api_client, email="three@example.com")
        responses = _post_watch(api_client, headers=headers, n=3)
        assert all(r.status_code == 200 for r in responses)

    def test_free_user_fourth_watch_returns_402(self, api_client) -> None:
        _, headers = signup_and_auth(api_client, email="four@example.com")
        _post_watch(api_client, headers=headers, n=3)
        body = {
            "facility_id": "fac_4",
            "name": "Watch 4",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "min_nights": 1,
        }
        resp = api_client.post("/api/watches", json=body, headers=headers)
        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert detail["error"] == "watch_limit_reached"
        assert detail["limit"] == 3
        assert detail["current"] == 3
        assert detail["upgrade_url"] == "/pricing"

    def test_pro_user_can_create_more_than_three(self, api_client) -> None:
        user_data, headers = signup_and_auth(
            api_client, email="prowatch@example.com",
        )
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], subscription_status="pro",
        )
        # 5 watches — well past free tier — all must succeed
        responses = _post_watch(api_client, headers=headers, n=5)
        assert all(r.status_code == 200 for r in responses), [
            (r.status_code, r.json()) for r in responses
        ]

    def test_anonymous_session_also_capped(self, api_client) -> None:
        # Anonymous users get the free-tier cap via session_token tracking.
        # Otherwise the cap is trivially bypassed by clearing the session.
        _post_watch(api_client, n=3)  # uses cookies via TestClient default
        body = {
            "facility_id": "anon_4",
            "name": "Anon 4",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "min_nights": 1,
        }
        resp = api_client.post("/api/watches", json=body)
        assert resp.status_code == 402

    def test_402_response_shape_machine_readable(self, api_client) -> None:
        # Frontend will read error.detail.error to decide which upgrade flow
        # to render. Lock in the shape so a future refactor doesn't quietly
        # break the upgrade prompt.
        _, headers = signup_and_auth(api_client, email="shape@example.com")
        _post_watch(api_client, headers=headers, n=3)
        body = {
            "facility_id": "fac_x",
            "name": "x",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "min_nights": 1,
        }
        resp = api_client.post("/api/watches", json=body, headers=headers)
        detail = resp.json()["detail"]
        assert set(detail.keys()) == {
            "error", "limit", "current", "upgrade_url",
        }


# ---------------------------------------------------------------------------
# Planner session enforcement (slice 4a)
# ---------------------------------------------------------------------------


def _start_chat(client, headers=None, content="plan me a trip"):
    return client.post(
        "/api/plan/chat",
        json={"messages": [{"role": "user", "content": content}]},
        headers=headers or {},
    )


class TestPlannerSessionEnforcement:
    @pytest.fixture(autouse=True)
    def _reset_plan_state(self, monkeypatch, api_client):
        """Each test starts with a clean IP rate-limit + a permissive cap.

        The route-level _PLAN_DAILY_LIMIT (5/day per IP) is an anti-abuse
        limit independent of the tier cap we're testing; TestClient reuses
        the same IP across calls, so without this we'd hit 429 before the
        v1.4 402. Depends on api_client so the watch_db reset hits the
        current (not torn-down) DB instance.
        """
        import pnw_campsites.routes.planner as planner_mod

        monkeypatch.setattr(planner_mod, "_PLAN_DAILY_LIMIT", 10_000)
        planner_mod._plan_rate_limit.clear()
        yield

    def test_free_user_first_three_succeed(self, api_client, monkeypatch) -> None:
        # Skip the actual LLM call — we're testing gating, not chat behaviour.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch(
            "pnw_campsites.planner.agent.chat",
            return_value={"role": "assistant", "content": "ok", "tool_calls": []},
        ):
            _, headers = signup_and_auth(
                api_client, email="planner1@example.com",
            )
            for _ in range(3):
                resp = _start_chat(api_client, headers=headers)
                assert resp.status_code == 200, resp.json()

    def test_free_user_fourth_session_returns_402(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch(
            "pnw_campsites.planner.agent.chat",
            return_value={"role": "assistant", "content": "ok", "tool_calls": []},
        ):
            _, headers = signup_and_auth(
                api_client, email="planner4@example.com",
            )
            for _ in range(3):
                _start_chat(api_client, headers=headers)
            resp = _start_chat(api_client, headers=headers)

        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert detail["error"] == "planner_session_limit_reached"
        assert detail["limit"] == 3
        assert detail["upgrade_url"] == "/pricing"

    def test_pro_user_can_exceed_free_limit(
        self, api_client, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        user_data, headers = signup_and_auth(
            api_client, email="proplan@example.com",
        )
        import pnw_campsites.api as api_module
        api_module._watch_db.update_user(
            user_data["id"], subscription_status="pro",
        )

        with patch(
            "pnw_campsites.planner.agent.chat",
            return_value={"role": "assistant", "content": "ok", "tool_calls": []},
        ):
            # 5 sessions — well past free cap, well under Pro cap of 20
            for i in range(5):
                resp = _start_chat(api_client, headers=headers)
                assert resp.status_code == 200, f"iteration {i}: {resp.json()}"

    def test_continuation_messages_dont_count(
        self, api_client, monkeypatch,
    ) -> None:
        # Multi-turn messages within an existing conversation must NOT
        # consume from the session budget — otherwise refreshing a long
        # trip-planning chat would burn through the cap in minutes.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        user_data, headers = signup_and_auth(
            api_client, email="multi@example.com",
        )
        with patch(
            "pnw_campsites.planner.agent.chat",
            return_value={"role": "assistant", "content": "ok", "tool_calls": []},
        ):
            # 1 session starter
            assert _start_chat(api_client, headers=headers).status_code == 200
            # Continuation: 3 messages — should not count as new sessions
            for _ in range(10):
                resp = api_client.post(
                    "/api/plan/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "hi"},
                            {"role": "assistant", "content": "hi back"},
                            {"role": "user", "content": "more"},
                        ],
                    },
                    headers=headers,
                )
                assert resp.status_code == 200

        # Only 1 session logged → user still has 2 starters left
        import pnw_campsites.api as api_module
        count = api_module._watch_db.count_planner_sessions_this_month(
            user_id=user_data["id"],
        )
        assert count == 1

    def test_anonymous_session_also_capped(
        self, api_client, monkeypatch,
    ) -> None:
        # Anonymous users must be capped by session_token so the limit
        # can't be bypassed by signing out / clearing cookies repeatedly.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch(
            "pnw_campsites.planner.agent.chat",
            return_value={"role": "assistant", "content": "ok", "tool_calls": []},
        ):
            # Use TestClient cookies (sticky across calls)
            for _ in range(3):
                _start_chat(api_client)
            resp = _start_chat(api_client)

        assert resp.status_code == 402
        assert resp.json()["detail"]["error"] == "planner_session_limit_reached"
