"""Tests for WatchDB user and search history methods."""

import json
import sqlite3

import pytest

from pnw_campsites.monitor.db import User, Watch, WatchDB


class TestUserCRUD:
    """Test user creation, reading, updating, and deletion."""

    def test_create_user_and_get_by_id(self, watch_db: WatchDB) -> None:
        """create_user + get_user_by_id round-trip."""
        user = User(
            email="alice@example.com",
            password_hash="hashed_pwd",
            display_name="Alice",
            home_base="Bellevue, WA",
            default_state="WA",
            default_nights=2,
            default_from="home",
        )
        created = watch_db.create_user(user)

        assert created.id is not None
        assert created.email == "alice@example.com"
        assert created.display_name == "Alice"
        assert created.created_at

        retrieved = watch_db.get_user_by_id(created.id)
        assert retrieved is not None
        assert retrieved.email == "alice@example.com"
        assert retrieved.display_name == "Alice"
        assert retrieved.home_base == "Bellevue, WA"
        assert retrieved.default_state == "WA"
        assert retrieved.default_nights == 2
        assert retrieved.default_from == "home"

    def test_get_user_by_id_not_found(self, watch_db: WatchDB) -> None:
        """get_user_by_id returns None for missing user."""
        result = watch_db.get_user_by_id(999)
        assert result is None

    def test_update_user_single_field(self, watch_db: WatchDB) -> None:
        """update_user updates a single field."""
        user = User(
            email="charlie@example.com",
            password_hash="hashed_pwd",
            display_name="Charlie",
            home_base="Seattle, WA",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        updated = watch_db.update_user(user_id, display_name="Charles")
        assert updated is not None
        assert updated.display_name == "Charles"
        assert updated.home_base == "Seattle, WA"  # Unchanged

        # Verify persistence
        retrieved = watch_db.get_user_by_id(user_id)
        assert retrieved is not None
        assert retrieved.display_name == "Charles"

    def test_update_user_multiple_fields(self, watch_db: WatchDB) -> None:
        """update_user updates multiple fields at once."""
        user = User(
            email="diana@example.com",
            password_hash="hashed_pwd",
            display_name="Diana",
            default_state="WA",
            default_nights=2,
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        updated = watch_db.update_user(
            user_id,
            display_name="Diana Prince",
            default_state="OR",
            default_nights=3,
        )
        assert updated is not None
        assert updated.display_name == "Diana Prince"
        assert updated.default_state == "OR"
        assert updated.default_nights == 3

    def test_update_user_last_login(self, watch_db: WatchDB) -> None:
        """update_user can set last_login_at."""
        user = User(
            email="eve@example.com",
            password_hash="hashed_pwd",
            display_name="Eve",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        login_time = "2026-03-22T14:30:00"
        updated = watch_db.update_user(user_id, last_login_at=login_time)
        assert updated is not None
        assert updated.last_login_at == login_time

    def test_update_user_nonexistent(self, watch_db: WatchDB) -> None:
        """update_user returns None for nonexistent user."""
        result = watch_db.update_user(999, display_name="Nobody")
        assert result is None

    def test_update_user_ignores_disallowed_fields(self, watch_db: WatchDB) -> None:
        """update_user ignores fields not in allowed list."""
        user = User(
            email="frank@example.com",
            password_hash="original_hash",
            display_name="Frank",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Try to update password_hash (not allowed) and email (not allowed)
        updated = watch_db.update_user(
            user_id,
            password_hash="new_hash",
            email="new@example.com",
            display_name="Franco",
        )
        assert updated is not None
        assert updated.display_name == "Franco"
        # password_hash and email should be unchanged
        assert updated.password_hash == "original_hash"
        assert updated.email == "frank@example.com"

    def test_delete_user(self, watch_db: WatchDB) -> None:
        """delete_user removes a user."""
        user = User(
            email="grace@example.com",
            password_hash="hashed_pwd",
            display_name="Grace",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Verify user exists
        assert watch_db.get_user_by_id(user_id) is not None

        # Delete
        result = watch_db.delete_user(user_id)
        assert result is True

        # Verify deletion
        assert watch_db.get_user_by_id(user_id) is None

    def test_delete_user_nonexistent(self, watch_db: WatchDB) -> None:
        """delete_user returns False for nonexistent user."""
        result = watch_db.delete_user(999)
        assert result is False

    def test_delete_user_cascades_watches(self, watch_db: WatchDB) -> None:
        """delete_user cascades and removes associated watches."""
        user = User(
            email="hank@example.com",
            password_hash="hashed_pwd",
            display_name="Hank",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Create a watch owned by this user
        watch = Watch(
            facility_id="232465",
            name="Ohanapecosh",
            start_date="2026-06-01",
            end_date="2026-06-30",
            min_nights=2,
            user_id=user_id,
        )
        watch_db.add_watch(watch)

        # Verify watch exists
        watches = watch_db.list_watches_by_user(user_id)
        assert len(watches) == 1

        # Delete user
        watch_db.delete_user(user_id)

        # Verify watch is also deleted
        watches_after = watch_db.list_watches_by_user(user_id)
        assert len(watches_after) == 0

    def test_delete_user_cascades_search_history(self, watch_db: WatchDB) -> None:
        """delete_user cascades and removes associated search history."""
        user = User(
            email="iris@example.com",
            password_hash="hashed_pwd",
            display_name="Iris",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Save a search
        params = json.dumps({"state": "WA", "nights": 2})
        watch_db.save_search(user_id, params, result_count=5)

        # Verify search exists
        history = watch_db.get_search_history(user_id)
        assert len(history) == 1

        # Delete user
        watch_db.delete_user(user_id)

        # Verify search history is also deleted
        history_after = watch_db.get_search_history(user_id)
        assert len(history_after) == 0


class TestSupabaseId:
    """Tests for supabase_id column and lookup."""

    def test_create_user_with_supabase_id(self, watch_db: WatchDB) -> None:
        user = User(
            email="supabase@example.com",
            password_hash="",
            supabase_id="550e8400-e29b-41d4-a716-446655440000",
        )
        created = watch_db.create_user(user)
        assert created.supabase_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_get_user_by_supabase_id(self, watch_db: WatchDB) -> None:
        sub = "660e8400-e29b-41d4-a716-446655440001"
        watch_db.create_user(User(email="lookup@example.com", password_hash="", supabase_id=sub))
        found = watch_db.get_user_by_supabase_id(sub)
        assert found is not None
        assert found.email == "lookup@example.com"

    def test_get_user_by_supabase_id_not_found(self, watch_db: WatchDB) -> None:
        assert watch_db.get_user_by_supabase_id("nonexistent-uuid") is None

    def test_supabase_id_uniqueness(self, watch_db: WatchDB) -> None:
        sub = "770e8400-e29b-41d4-a716-446655440002"
        watch_db.create_user(User(email="first@example.com", password_hash="", supabase_id=sub))
        with pytest.raises(sqlite3.IntegrityError):
            watch_db.create_user(User(email="second@example.com", password_hash="", supabase_id=sub))


class TestSearchHistory:
    """Test search history saving and retrieval."""

    def test_save_search_and_get_history(self, watch_db: WatchDB) -> None:
        """save_search + get_search_history round-trip."""
        user = User(
            email="jack@example.com",
            password_hash="hashed_pwd",
            display_name="Jack",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        params = json.dumps({"state": "WA", "nights": 2, "days": "fri,sat,sun"})
        watch_db.save_search(user_id, params, result_count=12)

        history = watch_db.get_search_history(user_id)
        assert len(history) == 1
        assert history[0]["params"] == {
            "state": "WA",
            "nights": 2,
            "days": "fri,sat,sun",
        }
        assert history[0]["result_count"] == 12
        assert history[0]["searched_at"]

    def test_get_search_history_multiple_entries(self, watch_db: WatchDB) -> None:
        """get_search_history returns multiple entries in DESC order."""
        user = User(
            email="kate@example.com",
            password_hash="hashed_pwd",
            display_name="Kate",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Save multiple searches
        watch_db.save_search(user_id, json.dumps({"state": "WA"}), result_count=5)
        watch_db.save_search(user_id, json.dumps({"state": "OR"}), result_count=8)
        watch_db.save_search(user_id, json.dumps({"state": "ID"}), result_count=3)

        history = watch_db.get_search_history(user_id)
        assert len(history) == 3
        # Most recent first
        assert history[0]["params"]["state"] == "ID"
        assert history[1]["params"]["state"] == "OR"
        assert history[2]["params"]["state"] == "WA"

    def test_get_search_history_respects_limit(self, watch_db: WatchDB) -> None:
        """get_search_history respects the limit parameter."""
        user = User(
            email="leo@example.com",
            password_hash="hashed_pwd",
            display_name="Leo",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        # Save 5 searches
        for i in range(5):
            watch_db.save_search(user_id, json.dumps({"search": i}), result_count=i)

        # Retrieve with limit=2
        history = watch_db.get_search_history(user_id, limit=2)
        assert len(history) == 2

        # Retrieve with limit=10 (more than exists)
        history = watch_db.get_search_history(user_id, limit=10)
        assert len(history) == 5

    def test_get_search_history_empty_for_new_user(self, watch_db: WatchDB) -> None:
        """get_search_history returns empty list for user with no searches."""
        user = User(
            email="mona@example.com",
            password_hash="hashed_pwd",
            display_name="Mona",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        history = watch_db.get_search_history(user_id)
        assert history == []

    def test_save_search_with_zero_result_count(self, watch_db: WatchDB) -> None:
        """save_search defaults result_count to 0."""
        user = User(
            email="nick@example.com",
            password_hash="hashed_pwd",
            display_name="Nick",
        )
        created = watch_db.create_user(user)
        user_id = created.id
        assert user_id is not None

        params = json.dumps({"state": "WA"})
        watch_db.save_search(user_id, params)  # No result_count provided

        history = watch_db.get_search_history(user_id)
        assert len(history) == 1
        assert history[0]["result_count"] == 0

    def test_save_search_isolation_per_user(self, watch_db: WatchDB) -> None:
        """Each user's search history is isolated."""
        user1 = User(
            email="olive@example.com",
            password_hash="hashed_pwd",
            display_name="Olive",
        )
        user2 = User(
            email="percy@example.com",
            password_hash="hashed_pwd",
            display_name="Percy",
        )
        created1 = watch_db.create_user(user1)
        created2 = watch_db.create_user(user2)
        user1_id = created1.id
        user2_id = created2.id
        assert user1_id is not None
        assert user2_id is not None

        watch_db.save_search(user1_id, json.dumps({"state": "WA"}), result_count=5)
        watch_db.save_search(user2_id, json.dumps({"state": "OR"}), result_count=3)

        history1 = watch_db.get_search_history(user1_id)
        history2 = watch_db.get_search_history(user2_id)

        assert len(history1) == 1
        assert history1[0]["params"]["state"] == "WA"
        assert len(history2) == 1
        assert history2[0]["params"]["state"] == "OR"


class TestWatchMigration:
    """Test migrating anonymous watches to user accounts."""

    def test_migrate_watches_to_user(self, watch_db: WatchDB) -> None:
        """migrate_watches_to_user sets user_id and clears session_token."""
        # Create an anonymous watch with session_token
        watch = Watch(
            facility_id="232465",
            name="Ohanapecosh",
            start_date="2026-06-01",
            end_date="2026-06-30",
            session_token="abc123",
            user_id=None,
        )
        watch_db.add_watch(watch)

        # Create a user to migrate to
        user = User(
            email="quinn@example.com",
            password_hash="hashed_pwd",
            display_name="Quinn",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Migrate the watch
        count = watch_db.migrate_watches_to_user("abc123", user_id)
        assert count == 1

        # Verify the watch now has user_id and no session_token
        retrieved_watch = watch_db.get_watch(watch.id)
        assert retrieved_watch is not None
        assert retrieved_watch.user_id == user_id
        assert retrieved_watch.session_token == ""

    def test_migrate_watches_multiple(self, watch_db: WatchDB) -> None:
        """migrate_watches_to_user handles multiple watches with same token."""
        # Create multiple anonymous watches with same session_token
        token = "session_xyz"
        for i in range(3):
            watch = Watch(
                facility_id=f"facility_{i}",
                name=f"Park {i}",
                start_date="2026-06-01",
                end_date="2026-06-30",
                session_token=token,
                user_id=None,
            )
            watch_db.add_watch(watch)

        # Create user
        user = User(
            email="rosa@example.com",
            password_hash="hashed_pwd",
            display_name="Rosa",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Migrate all watches
        count = watch_db.migrate_watches_to_user(token, user_id)
        assert count == 3

        # Verify all are migrated
        watches = watch_db.list_watches_by_user(user_id)
        assert len(watches) == 3
        for w in watches:
            assert w.user_id == user_id
            assert w.session_token == ""

    def test_migrate_watches_nonexistent_token(self, watch_db: WatchDB) -> None:
        """migrate_watches_to_user returns 0 for nonexistent token."""
        user = User(
            email="sam@example.com",
            password_hash="hashed_pwd",
            display_name="Sam",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        count = watch_db.migrate_watches_to_user("nonexistent_token", user_id)
        assert count == 0

    def test_list_watches_by_user(self, watch_db: WatchDB) -> None:
        """list_watches_by_user returns only that user's watches."""
        user1 = User(
            email="tina@example.com",
            password_hash="hashed_pwd",
            display_name="Tina",
        )
        user2 = User(
            email="uma@example.com",
            password_hash="hashed_pwd",
            display_name="Uma",
        )
        created1 = watch_db.create_user(user1)
        created2 = watch_db.create_user(user2)
        user1_id = created1.id
        user2_id = created2.id
        assert user1_id is not None
        assert user2_id is not None

        # Add watches to user1
        for i in range(2):
            watch = Watch(
                facility_id=f"facility_{i}",
                name=f"Park {i}",
                start_date="2026-06-01",
                end_date="2026-06-30",
                user_id=user1_id,
            )
            watch_db.add_watch(watch)

        # Add watch to user2
        watch = Watch(
            facility_id="facility_other",
            name="Other Park",
            start_date="2026-07-01",
            end_date="2026-07-31",
            user_id=user2_id,
        )
        watch_db.add_watch(watch)

        # Verify isolation
        watches1 = watch_db.list_watches_by_user(user1_id)
        watches2 = watch_db.list_watches_by_user(user2_id)

        assert len(watches1) == 2
        assert len(watches2) == 1
        assert all(w.user_id == user1_id for w in watches1)
        assert watches2[0].user_id == user2_id

    def test_list_watches_by_user_empty(self, watch_db: WatchDB) -> None:
        """list_watches_by_user returns empty list if user has no watches."""
        user = User(
            email="victor@example.com",
            password_hash="hashed_pwd",
            display_name="Victor",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        watches = watch_db.list_watches_by_user(user_id)
        assert watches == []

    def test_list_watches_by_user_ordered_by_created_at(
        self, watch_db: WatchDB
    ) -> None:
        """list_watches_by_user returns watches in DESC created_at order."""
        user = User(
            email="wilma@example.com",
            password_hash="hashed_pwd",
            display_name="Wilma",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Add watches (will have ascending created_at)
        watch_ids = []
        for i in range(3):
            watch = Watch(
                facility_id=f"facility_{i}",
                name=f"Park {i}",
                start_date="2026-06-01",
                end_date="2026-06-30",
                user_id=user_id,
            )
            added = watch_db.add_watch(watch)
            watch_ids.append(added.id)

        watches = watch_db.list_watches_by_user(user_id)
        # Most recent first
        assert watches[0].id == watch_ids[2]
        assert watches[1].id == watch_ids[1]
        assert watches[2].id == watch_ids[0]


class TestUserExport:
    """Test get_user_export method."""

    def test_get_user_export_basic(self, watch_db: WatchDB) -> None:
        """get_user_export returns dict with user info, watches, and history."""
        user = User(
            email="xavier@example.com",
            password_hash="hashed_pwd",
            display_name="Xavier",
            home_base="Portland, OR",
            default_state="OR",
            default_nights=3,
            default_from="home",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        export = watch_db.get_user_export(user_id)

        assert "user" in export
        assert "watches" in export
        assert "search_history" in export

        assert export["user"]["email"] == "xavier@example.com"
        assert export["user"]["display_name"] == "Xavier"
        assert export["user"]["home_base"] == "Portland, OR"
        assert export["user"]["default_state"] == "OR"
        assert export["user"]["default_nights"] == 3
        assert export["user"]["default_from"] == "home"
        assert export["user"]["created_at"]

    def test_get_user_export_with_watches(self, watch_db: WatchDB) -> None:
        """get_user_export includes user's watches."""
        user = User(
            email="yara@example.com",
            password_hash="hashed_pwd",
            display_name="Yara",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Add a watch
        watch = Watch(
            facility_id="232465",
            name="Ohanapecosh",
            start_date="2026-06-01",
            end_date="2026-06-30",
            min_nights=2,
            user_id=user_id,
            enabled=True,
        )
        watch_db.add_watch(watch)

        export = watch_db.get_user_export(user_id)

        assert len(export["watches"]) == 1
        assert export["watches"][0]["facility_id"] == "232465"
        assert export["watches"][0]["name"] == "Ohanapecosh"
        assert export["watches"][0]["start_date"] == "2026-06-01"
        assert export["watches"][0]["end_date"] == "2026-06-30"
        assert export["watches"][0]["min_nights"] == 2
        assert export["watches"][0]["enabled"] is True
        assert export["watches"][0]["created_at"]

    def test_get_user_export_with_search_history(self, watch_db: WatchDB) -> None:
        """get_user_export includes user's search history."""
        user = User(
            email="zara@example.com",
            password_hash="hashed_pwd",
            display_name="Zara",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Save searches
        watch_db.save_search(
            user_id, json.dumps({"state": "WA", "nights": 2}), result_count=10
        )
        watch_db.save_search(
            user_id, json.dumps({"state": "OR", "nights": 1}), result_count=5
        )

        export = watch_db.get_user_export(user_id)

        assert len(export["search_history"]) == 2
        assert export["search_history"][0]["params"]["state"] == "OR"
        assert export["search_history"][0]["result_count"] == 5
        assert export["search_history"][1]["params"]["state"] == "WA"
        assert export["search_history"][1]["result_count"] == 10

    def test_get_user_export_nonexistent_user(self, watch_db: WatchDB) -> None:
        """get_user_export returns empty dict for nonexistent user."""
        export = watch_db.get_user_export(999)
        assert export == {}

    def test_get_user_export_limits_history(self, watch_db: WatchDB) -> None:
        """get_user_export limits search history to 100 entries."""
        user = User(
            email="alpha@example.com",
            password_hash="hashed_pwd",
            display_name="Alpha",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        # Save 120 searches
        for i in range(120):
            watch_db.save_search(user_id, json.dumps({"search": i}), result_count=i)

        export = watch_db.get_user_export(user_id)

        # Should be limited to 100
        assert len(export["search_history"]) == 100

    def test_save_push_subscription_round_trip(self, watch_db: WatchDB) -> None:
        """save_push_subscription and get_push_subscriptions_for_user."""
        user = User(
            email="push@example.com",
            password_hash="hash",
            display_name="Push User",
        )
        created_user = watch_db.create_user(user)
        user_id = created_user.id
        assert user_id is not None

        subscription = {
            "endpoint": "https://push.example.com/sub1",
            "p256dh": "p256dh_key",
            "auth": "auth_key",
        }

        watch_db.save_push_subscription(
            user_id=user_id,
            session_token="session_123",
            endpoint=subscription["endpoint"],
            p256dh=subscription["p256dh"],
            auth=subscription["auth"],
        )

        subs = watch_db.get_push_subscriptions_for_user(user_id)

        assert len(subs) == 1
        assert subs[0]["endpoint"] == subscription["endpoint"]
        assert subs[0]["p256dh"] == subscription["p256dh"]
        assert subs[0]["auth"] == subscription["auth"]

    def test_log_notification_persists(self, watch_db: WatchDB) -> None:
        """log_notification saves notification log entry."""
        watch = Watch(
            id=None,
            facility_id="123",
            name="Test Watch",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        created_watch = watch_db.add_watch(watch)
        watch_id = created_watch.id
        assert watch_id is not None

        watch_db.log_notification(
            watch_id=watch_id,
            channel="web_push",
            status="sent",
            changes_count=3,
        )

        # Verify it was inserted by querying directly
        row = watch_db._conn.execute(
            "SELECT * FROM notification_log WHERE watch_id=?",
            (watch_id,),
        ).fetchone()

        assert row is not None
        assert row["channel"] == "web_push"
        assert row["status"] == "sent"
        assert row["changes_count"] == 3

    def test_get_recent_notifications_returns_list(self, watch_db: WatchDB) -> None:
        """get_recent_notifications returns list of dicts."""
        watch = Watch(
            id=None,
            facility_id="123",
            name="Test Watch",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        created_watch = watch_db.add_watch(watch)
        watch_id = created_watch.id
        assert watch_id is not None

        watch_db.log_notification(
            watch_id=watch_id,
            channel="pushover",
            status="sent",
            changes_count=1,
        )

        notifications = watch_db.get_recent_notifications(limit=10)

        assert isinstance(notifications, list)
        # Should have at least some notification
        assert len(notifications) > 0
        # Check structure
        if notifications:
            assert "channel" in notifications[0]
            assert "status" in notifications[0]

