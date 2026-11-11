"""Release reminders fire at 6:55 am PT on release day, then become watches."""

from __future__ import annotations

from datetime import datetime

import pytest

from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.reminders import (
    PACIFIC,
    reminder_push,
    run_release_reminders,
)


def _pt(d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 11, d, hh, mm, tzinfo=PACIFIC)


class Sender:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.fail = fail

    async def __call__(self, subscription: dict, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("push service down")
        self.sent.append((subscription["endpoint"], payload))


@pytest.fixture
def user_id(watch_db: WatchDB) -> int:
    from pnw_campsites.monitor.db import User

    user = watch_db.create_user(User(email="a@example.com"))
    watch_db.save_push_subscription(user.id, "", "https://push/1", "p", "a")
    return user.id


def _reminder(watch_db: WatchDB, user_id: int, **kw) -> Watch:
    base = dict(
        facility_id="232465", name="Kachess", start_date="2027-05-21",
        end_date="2027-05-22", min_nights=2, user_id=user_id,
        notification_channel="web_push", watch_type="release",
        releases_on="2026-11-21", min_people=4, equipment="trailer", rig_length=30,
    )
    base.update(kw)
    return watch_db.add_watch(Watch(**base))


class TestRunReleaseReminders:
    @pytest.mark.asyncio
    async def test_nothing_before_six_fifty_five(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        send = Sender()
        await run_release_reminders(watch_db, now=_pt(21, 6, 54), send=send)
        assert send.sent == []
        assert watch_db.get_watch(watch.id).watch_type == "release"

    @pytest.mark.asyncio
    async def test_pushes_once_and_converts_keeping_filters(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        send = Sender()
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=send)
        await run_release_reminders(watch_db, now=_pt(21, 7, 10), send=send)
        assert [endpoint for endpoint, _ in send.sent] == ["https://push/1"]
        got = watch_db.get_watch(watch.id)
        assert got.watch_type == "single"
        assert (got.min_people, got.equipment, got.rig_length) == (4, "trailer", 30)
        assert (got.start_date, got.end_date, got.min_nights) == (
            "2027-05-21", "2027-05-22", 2,
        )

    @pytest.mark.asyncio
    async def test_missed_release_day_converts_without_push(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        send = Sender()
        await run_release_reminders(watch_db, now=_pt(23, 6, 55), send=send)
        assert send.sent == []
        assert watch_db.get_watch(watch.id).watch_type == "single"

    @pytest.mark.asyncio
    async def test_failed_push_still_converts(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=Sender(fail=True))
        assert watch_db.get_watch(watch.id).watch_type == "single"

    @pytest.mark.asyncio
    async def test_paused_reminder_is_left_alone(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        watch_db.toggle_enabled(watch.id)
        send = Sender()
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=send)
        assert send.sent == []
        assert watch_db.get_watch(watch.id).watch_type == "release"

    @pytest.mark.asyncio
    async def test_bad_release_date_converts(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id, releases_on="not-a-date")
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=Sender())
        assert watch_db.get_watch(watch.id).watch_type == "single"

    @pytest.mark.asyncio
    async def test_other_watches_are_untouched(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id, watch_type="single", releases_on=None)
        send = Sender()
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=send)
        assert send.sent == []
        assert watch_db.get_watch(watch.id).watch_type == "single"

    @pytest.mark.asyncio
    async def test_push_is_logged(self, watch_db, user_id):
        watch = _reminder(watch_db, user_id)
        await run_release_reminders(watch_db, now=_pt(21, 6, 55), send=Sender())
        logged = watch_db._conn.execute(
            "SELECT channel, status FROM notification_log WHERE watch_id=?", (watch.id,),
        ).fetchall()
        assert [tuple(r) for r in logged] == [("web_push", "sent")]


class TestReminderPush:
    def test_recgov_names_the_seven_am_release(self):
        push = reminder_push(Watch(
            facility_id="232465", name="Kachess", start_date="2027-05-21",
            end_date="2027-05-22", booking_system="recgov",
        ))
        assert push["title"] == "Kachess opens for booking at 7:00 am"
        assert push["body"].startswith("Fri May 21 – Sat May 22.")
        assert "recreation.gov" in push["url"]

    def test_other_systems_say_today(self):
        push = reminder_push(Watch(
            facility_id="-2147483624", name="Deception Pass", start_date="2027-08-06",
            end_date="2027-08-07", booking_system="wa_state",
        ))
        assert push["title"] == "Deception Pass opens for booking today"
        assert push["body"].startswith("Fri Aug 6 – Sat Aug 7.")
