"""Native (APNs) device tokens: storage and the registration endpoint.

A device token is the address APNs delivers to. Whoever holds the row for a
token gets that phone's alerts, so registration needs a signed-in user, a
token moves with the account that last registered it, and removal is scoped
to the caller.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from pnw_campsites import api as api_module
from pnw_campsites.monitor.db import User, WatchDB
from tests.conftest import signup_and_auth

TOKEN = "a1" * 32  # 64 hex chars, the shape iOS hands out
OTHER = "b2" * 32


def _user(db: WatchDB, email: str) -> int:
    return db.create_user(User(email=email, password_hash="")).id


class TestStorage:
    def test_save_and_list(self, watch_db: WatchDB):
        uid = _user(watch_db, "a@example.com")
        watch_db.save_device_token(uid, TOKEN)
        assert watch_db.get_device_tokens_for_user(uid) == [TOKEN]

    def test_reregistering_moves_the_token_to_the_new_account(self, watch_db):
        a = _user(watch_db, "a@example.com")
        b = _user(watch_db, "b@example.com")
        watch_db.save_device_token(a, TOKEN)
        watch_db.save_device_token(b, TOKEN)
        assert watch_db.get_device_tokens_for_user(a) == []
        assert watch_db.get_device_tokens_for_user(b) == [TOKEN]

    def test_scoped_delete_only_removes_the_callers_token(self, watch_db):
        a = _user(watch_db, "a@example.com")
        b = _user(watch_db, "b@example.com")
        watch_db.save_device_token(a, TOKEN)
        watch_db.delete_device_token(TOKEN, user_id=b)
        assert watch_db.get_device_tokens_for_user(a) != []
        watch_db.delete_device_token(TOKEN, user_id=a)
        assert watch_db.get_device_tokens_for_user(a) == []

    def test_unscoped_delete_for_dead_tokens(self, watch_db):
        uid = _user(watch_db, "a@example.com")
        watch_db.save_device_token(uid, TOKEN)
        watch_db.delete_device_token(TOKEN)
        assert watch_db.get_device_tokens_for_user(uid) == []

    def test_account_deletion_removes_tokens(self, watch_db):
        uid = _user(watch_db, "a@example.com")
        watch_db.save_device_token(uid, TOKEN)
        watch_db.delete_user(uid)
        count = watch_db._conn.execute(
            "SELECT COUNT(*) FROM device_push_tokens",
        ).fetchone()[0]
        assert count == 0

    def test_keeps_at_most_five_tokens_per_user(self, watch_db):
        uid = _user(watch_db, "a@example.com")
        tokens = [f"{i:064x}" for i in range(7)]
        for t in tokens:
            watch_db.save_device_token(uid, t)
        kept = watch_db.get_device_tokens_for_user(uid)
        assert kept == tokens[2:]

    def test_migration_is_idempotent_on_an_existing_db(self, tmp_path):
        path = tmp_path / "w.db"
        WatchDB(path).close()
        db = WatchDB(path)  # second open re-runs _migrate
        uid = _user(db, "a@example.com")
        db.save_device_token(uid, TOKEN)
        db.close()
        db = WatchDB(path)
        assert len(db.get_device_tokens_for_user(uid)) == 1
        db.close()

    def test_migration_on_a_db_created_before_device_tokens(self, tmp_path):
        """Old prod DBs have users and push_subscriptions but no token table."""
        path = tmp_path / "old.db"
        WatchDB(path).close()
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE device_push_tokens")
        conn.commit()
        conn.close()
        db = WatchDB(path)
        uid = _user(db, "a@example.com")
        db.save_device_token(uid, TOKEN)
        assert len(db.get_device_tokens_for_user(uid)) == 1
        db.close()


class TestEndpoint:
    def test_requires_a_signed_in_user(self, api_client: TestClient):
        resp = api_client.post(
            "/api/push/device-token", json={"token": TOKEN, "platform": "ios"},
        )
        assert resp.status_code == 401
        assert api_module._watch_db._conn.execute(
            "SELECT COUNT(*) FROM device_push_tokens",
        ).fetchone()[0] == 0

    def test_registers_for_the_bearer_user(self, api_client: TestClient):
        user, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/push/device-token",
            json={"token": TOKEN, "platform": "ios"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert api_module._watch_db.get_device_tokens_for_user(user["id"]) == [TOKEN]

    def test_token_is_normalised_to_lowercase(self, api_client: TestClient):
        user, headers = signup_and_auth(api_client)
        api_client.post(
            "/api/push/device-token",
            json={"token": TOKEN.upper(), "platform": "ios"},
            headers=headers,
        )
        assert api_module._watch_db.get_device_tokens_for_user(user["id"]) == [TOKEN]

    def test_rejects_malformed_tokens(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client)
        for bad in ["", "zz" * 32, "a1" * 10, "a1" * 101, TOKEN + "/../x"]:
            resp = api_client.post(
                "/api/push/device-token",
                json={"token": bad, "platform": "ios"},
                headers=headers,
            )
            assert resp.status_code == 422, bad

    def test_rejects_other_platforms(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/push/device-token",
            json={"token": TOKEN, "platform": "android"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_delete_needs_only_the_token(self, api_client: TestClient):
        """Holding the token is the proof. An expired session must still be
        able to stop a shared phone getting the previous user's alerts."""
        a, a_headers = signup_and_auth(api_client, email="a@example.com")
        api_client.post(
            "/api/push/device-token",
            json={"token": TOKEN, "platform": "ios"},
            headers=a_headers,
        )
        resp = api_client.request(
            "DELETE", "/api/push/device-token", json={"token": TOKEN.upper()},
        )
        assert resp.status_code == 200
        assert api_module._watch_db.get_device_tokens_for_user(a["id"]) == []

    def test_unknown_fields_are_rejected(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/push/device-token",
            json={"token": TOKEN, "platform": "ios", "user_id": 1},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_daily_quota_per_user(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client)
        codes = [
            api_client.post(
                "/api/push/device-token",
                json={"token": f"{i:064x}", "platform": "ios"},
                headers=headers,
            ).status_code
            for i in range(31)
        ]
        assert codes[:30] == [200] * 30
        assert codes[30] == 429
