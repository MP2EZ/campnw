"""Deleting an account ends billing, analytics identity and sign-in (DEBUG-13)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import jwt as pyjwt
import pytest
import respx
from fastapi.testclient import TestClient
from stripe import InvalidRequestError, StripeError

import pnw_campsites.api as api_module
from pnw_campsites import billing
from tests.conftest import auth_headers, make_supabase_jwt

POSTHOG_BULK_DELETE = "https://eu.posthog.com/api/projects/4242/persons/bulk_delete/"


@pytest.fixture
def client(api_client: TestClient):
    with patch(
        "pnw_campsites.routes.auth._delete_supabase_user", new_callable=AsyncMock,
    ) as supabase_delete:
        api_client.supabase_delete = supabase_delete
        yield api_client


@pytest.fixture(autouse=True)
def _no_posthog_admin(monkeypatch):
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_PROJECT_ID", raising=False)


def _provision(client: TestClient) -> tuple[str, int]:
    token = make_supabase_jwt(supabase_id=str(uuid.uuid4()))
    user_id = client.get("/api/auth/me", headers=auth_headers(token)).json()["user"]["id"]
    return token, user_id


class _FakeSubscriptions:
    def __init__(self, active: list[str], fail_cancel: Exception | None = None,
                 fail_list: Exception | None = None):
        self.active = active
        self.fail_cancel = fail_cancel
        self.fail_list = fail_list
        self.listed: list[dict] = []
        self.cancelled: list[str] = []

    def list(self, params=None):
        self.listed.append(params or {})
        if self.fail_list:
            raise self.fail_list
        return type("L", (), {"data": [type("S", (), {"id": s})() for s in self.active]})()

    def cancel(self, subscription_id, params=None):
        if self.fail_cancel:
            raise self.fail_cancel
        self.cancelled.append(subscription_id)


def _fake_stripe(monkeypatch, subs: _FakeSubscriptions) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    fake = type("C", (), {})()
    fake.v1 = type("V1", (), {"subscriptions": subs})()
    monkeypatch.setattr(billing, "_get_client", lambda: fake)


# ---------------------------------------------------------------------------
# A still-valid token can't bring a deleted account back
# ---------------------------------------------------------------------------


class TestDeletedTokenCannotRecreate:

    def test_token_after_delete_is_rejected(self, client: TestClient):
        token, user_id = _provision(client)
        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200

        resp = client.get("/api/auth/me", headers=auth_headers(token))

        assert resp.status_code == 401
        db = api_module._watch_db
        assert db.get_user_by_id(user_id) is None
        sub = pyjwt.decode(token, options={"verify_signature": False})["sub"]
        assert db.get_user_by_supabase_id(sub) is None

    def test_logout_push_cleanup_does_not_recreate_user(self, client: TestClient):
        # The web client's logout runs right after delete and calls this
        # endpoint with the same token: it used to re-provision the account.
        token, _ = _provision(client)
        client.delete("/api/auth/me", headers=auth_headers(token))

        client.request(
            "DELETE", "/api/push/subscribe",
            headers=auth_headers(token),
            json={"endpoint": "https://push.example/x"},
        )

        assert api_module._watch_db._conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0] == 0

    def test_new_supabase_user_can_still_sign_up(self, client: TestClient):
        token, _ = _provision(client)
        client.delete("/api/auth/me", headers=auth_headers(token))

        fresh = make_supabase_jwt(supabase_id=str(uuid.uuid4()))
        assert client.get("/api/auth/me", headers=auth_headers(fresh)).status_code == 200


# ---------------------------------------------------------------------------
# Stripe subscription is cancelled
# ---------------------------------------------------------------------------


class TestStripeCancelledOnDelete:

    def test_active_subscription_is_cancelled(self, client: TestClient, monkeypatch):
        subs = _FakeSubscriptions(active=["sub_live_1"])
        _fake_stripe(monkeypatch, subs)
        token, user_id = _provision(client)
        api_module._watch_db.update_user(
            user_id, stripe_customer_id="cus_123", subscription_id="sub_live_1",
            subscription_status="pro",
        )

        resp = client.delete("/api/auth/me", headers=auth_headers(token))

        assert resp.status_code == 200
        assert subs.listed[0]["customer"] == "cus_123"
        assert subs.cancelled == ["sub_live_1"]
        assert api_module._watch_db.get_user_by_id(user_id) is None

    def test_every_open_subscription_is_cancelled(self, client: TestClient, monkeypatch):
        subs = _FakeSubscriptions(active=["sub_a", "sub_b"])
        _fake_stripe(monkeypatch, subs)
        token, user_id = _provision(client)
        api_module._watch_db.update_user(user_id, stripe_customer_id="cus_123")

        client.delete("/api/auth/me", headers=auth_headers(token))

        assert subs.cancelled == ["sub_a", "sub_b"]

    def test_no_customer_means_no_stripe_call(self, client: TestClient, monkeypatch):
        subs = _FakeSubscriptions(active=["sub_x"])
        _fake_stripe(monkeypatch, subs)
        token, _ = _provision(client)

        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200
        assert subs.listed == []

    def test_stripe_failure_keeps_account_and_sign_in(self, client: TestClient, monkeypatch):
        subs = _FakeSubscriptions(active=["sub_1"], fail_cancel=StripeError("boom"))
        _fake_stripe(monkeypatch, subs)
        token, user_id = _provision(client)
        api_module._watch_db.update_user(user_id, stripe_customer_id="cus_123")

        resp = client.delete("/api/auth/me", headers=auth_headers(token))

        assert resp.status_code == 502
        assert api_module._watch_db.get_user_by_id(user_id) is not None
        client.supabase_delete.assert_not_called()
        # The user can still sign in and retry.
        assert client.get("/api/auth/me", headers=auth_headers(token)).status_code == 200

    def test_customer_already_gone_in_stripe_is_fine(self, client: TestClient, monkeypatch):
        missing = InvalidRequestError("No such customer", param="customer", code="resource_missing")
        subs = _FakeSubscriptions(active=[], fail_list=missing)
        _fake_stripe(monkeypatch, subs)
        token, user_id = _provision(client)
        api_module._watch_db.update_user(user_id, stripe_customer_id="cus_gone")

        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200
        assert api_module._watch_db.get_user_by_id(user_id) is None


# ---------------------------------------------------------------------------
# PostHog person is deleted
# ---------------------------------------------------------------------------


@pytest.fixture
def posthog_admin(monkeypatch):
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "phx_test")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "4242")
    monkeypatch.setenv("POSTHOG_HOST", "https://eu.i.posthog.com")


class TestPosthogPersonDeleted:

    @respx.mock
    def test_person_deleted_by_user_id(self, respx_mock, client: TestClient, posthog_admin):
        route = respx_mock.post(POSTHOG_BULK_DELETE).mock(
            return_value=httpx.Response(202, json={"persons_queued_for_deletion": 1}),
        )
        token, user_id = _provision(client)

        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200

        assert route.called
        req = route.calls.last.request
        assert req.headers["Authorization"] == "Bearer phx_test"
        body = json.loads(req.content)
        assert body["distinct_ids"] == [str(user_id)]
        assert body["delete_events"] is True
        assert body["delete_recordings"] is True

    @respx.mock
    def test_posthog_failure_does_not_block_delete(
        self, respx_mock, client: TestClient, posthog_admin,
    ):
        respx_mock.post(POSTHOG_BULK_DELETE).mock(return_value=httpx.Response(500))
        token, user_id = _provision(client)

        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200
        assert api_module._watch_db.get_user_by_id(user_id) is None

    def test_unconfigured_posthog_is_skipped(self, client: TestClient):
        token, user_id = _provision(client)
        assert client.delete("/api/auth/me", headers=auth_headers(token)).status_code == 200
        assert api_module._watch_db.get_user_by_id(user_id) is None
