"""Release reminders (v1.48 P3d, D9): the watch type, its dates and the API."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from pnw_campsites.monitor import reminders
from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.reminders import PACIFIC, release_problem, reminder_action
from tests.conftest import signup_and_auth


def _pt(y: int, m: int, d: int, hh: int = 12, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=PACIFIC)


RELEASE = date(2026, 11, 21)


class TestReminderAction:
    def test_waits_before_release_day(self):
        assert reminder_action(RELEASE, _pt(2026, 11, 20, 23, 59)) == "wait"

    def test_waits_until_six_fifty_five_on_release_day(self):
        assert reminder_action(RELEASE, _pt(2026, 11, 21, 6, 54)) == "wait"

    def test_pushes_from_six_fifty_five_on_release_day(self):
        assert reminder_action(RELEASE, _pt(2026, 11, 21, 6, 55)) == "push"
        assert reminder_action(RELEASE, _pt(2026, 11, 21, 18, 0)) == "push"

    def test_converts_without_push_once_release_day_has_passed(self):
        assert reminder_action(RELEASE, _pt(2026, 11, 22, 6, 55)) == "convert"

    def test_reads_the_clock_in_pacific_time(self):
        from zoneinfo import ZoneInfo

        # 14:55 UTC on Nov 21 is 06:55 PST.
        utc = datetime(2026, 11, 21, 14, 55, tzinfo=ZoneInfo("UTC"))
        assert reminder_action(RELEASE, utc) == "push"


class TestReleaseProblem:
    NOW = _pt(2026, 11, 11, 9, 0)

    def test_future_release_before_the_stay_is_fine(self):
        assert release_problem("2026-11-21", "2027-05-21", self.NOW) is None

    def test_missing_or_malformed_date(self):
        assert release_problem(None, "2027-05-21", self.NOW) == "releases_on_required"
        assert release_problem("2026-02-30", "2027-05-21", self.NOW) == "releases_on_invalid"

    def test_already_released(self):
        assert release_problem("2026-11-10", "2027-05-21", self.NOW) == "already_released"

    def test_release_day_after_the_reminder_time_is_already_released(self):
        assert release_problem("2026-11-11", "2027-05-21", self.NOW) == "already_released"
        early = _pt(2026, 11, 11, 6, 0)
        assert release_problem("2026-11-11", "2027-05-21", early) is None

    def test_release_after_the_first_night_is_invalid(self):
        assert release_problem("2027-05-22", "2027-05-21", self.NOW) == "releases_on_invalid"


class TestReleaseWatchStorage:
    def test_releases_on_round_trips(self, watch_db: WatchDB):
        saved = watch_db.add_watch(Watch(
            facility_id="232465", start_date="2027-05-21", end_date="2027-05-22",
            watch_type="release", releases_on="2026-11-21",
        ))
        got = watch_db.get_watch(saved.id)
        assert (got.watch_type, got.releases_on) == ("release", "2026-11-21")

    def test_other_watches_have_no_release_date(self, watch_db: WatchDB):
        saved = watch_db.add_watch(Watch(
            facility_id="1", start_date="2027-05-21", end_date="2027-05-22",
        ))
        assert watch_db.get_watch(saved.id).releases_on is None

    def test_migration_adds_the_column_idempotently(self, tmp_path):
        path = tmp_path / "old.db"
        WatchDB(path).close()
        conn = sqlite3.connect(path)
        conn.execute("ALTER TABLE watches DROP COLUMN releases_on")
        conn.execute(
            "INSERT INTO watches (facility_id, start_date, end_date)"
            " VALUES ('1', '2027-05-21', '2027-05-22')"
        )
        conn.commit()
        conn.close()
        for _ in range(2):
            db = WatchDB(path)
            assert db.list_watches()[0].releases_on is None
            db.close()


@pytest.mark.asyncio
async def test_poller_skips_reminders(watch_db: WatchDB):
    from unittest.mock import AsyncMock

    from pnw_campsites.monitor.watcher import poll_all
    from pnw_campsites.providers.recgov import RecGovClient

    watch_db.add_watch(Watch(
        facility_id="232465", start_date="2027-05-21", end_date="2027-05-22",
        watch_type="release", releases_on="2026-11-21",
    ))
    client = AsyncMock(spec=RecGovClient)
    results = await poll_all(client, None, watch_db, today=date(2026, 11, 11))
    assert results == []
    client.get_availability_range.assert_not_called()


BODY = {
    "facility_id": "232465",
    "name": "Kachess",
    "start_date": "2027-05-21",
    "end_date": "2027-05-22",
    "min_nights": 2,
    "notification_channel": "web_push",
    "watch_type": "release",
    "releases_on": "2026-11-21",
}


@pytest.fixture
def at_nine_am(monkeypatch):
    monkeypatch.setattr(reminders, "pacific_now", lambda: _pt(2026, 11, 11, 9, 0))


class TestCreateReleaseReminder:
    def test_signed_in_user_creates_a_reminder(self, api_client, at_nine_am):
        _, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/watches", json={**BODY, "min_people": 4}, headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_type"] == "release"
        assert data["releases_on"] == "2026-11-21"
        assert data["min_people"] == 4
        listed = api_client.get("/api/watches", headers=headers).json()
        assert [w["releases_on"] for w in listed] == ["2026-11-21"]

    def test_reminder_defaults_to_push(self, api_client, at_nine_am):
        _, headers = signup_and_auth(api_client)
        body = {**BODY, "notification_channel": ""}
        data = api_client.post("/api/watches", json=body, headers=headers).json()
        assert data["notification_channel"] == "web_push"

    def test_signed_out_is_refused(self, api_client, at_nine_am):
        assert api_client.post("/api/watches", json=BODY).status_code == 401

    @pytest.mark.parametrize("releases_on,error", [
        (None, "releases_on_required"),
        ("2026-11-01", "already_released"),
        ("2027-06-01", "releases_on_invalid"),
    ])
    def test_bad_release_dates_are_rejected(
        self, api_client, at_nine_am, releases_on, error,
    ):
        _, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/watches", json={**BODY, "releases_on": releases_on}, headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == error

    def test_malformed_release_date_is_rejected(self, api_client, at_nine_am):
        _, headers = signup_and_auth(api_client)
        resp = api_client.post(
            "/api/watches", json={**BODY, "releases_on": "soon"}, headers=headers,
        )
        assert resp.status_code == 422

    def test_same_stay_twice_is_a_duplicate(self, api_client, at_nine_am):
        _, headers = signup_and_auth(api_client)
        assert api_client.post("/api/watches", json=BODY, headers=headers).status_code == 200
        assert api_client.post("/api/watches", json=BODY, headers=headers).status_code == 409

    def test_releases_on_is_ignored_on_other_watches(self, api_client, at_nine_am):
        body = {**BODY, "watch_type": "single"}
        data = api_client.post("/api/watches", json=body).json()
        assert data["releases_on"] is None
