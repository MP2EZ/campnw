"""Watches alert on stays of min_nights consecutive nights, not single nights."""

from __future__ import annotations

import pytest

from pnw_campsites.monitor.db import Snapshot, Watch, WatchDB
from pnw_campsites.monitor.stays import new_stay_nights, stay_starts
from pnw_campsites.monitor.watcher import poll_watch
from pnw_campsites.providers.recgov import RecGovClient
from tests.conftest import make_campground_availability, make_campsite_availability


class TestStayStarts:
    def test_one_night_stays_are_every_night(self):
        assert stay_starts(["2027-05-21", "2027-05-23"], 1) == {
            "2027-05-21", "2027-05-23",
        }

    def test_two_night_stays_need_consecutive_nights(self):
        dates = ["2027-05-21", "2027-05-22", "2027-05-23", "2027-05-25"]
        assert stay_starts(dates, 2) == {"2027-05-21", "2027-05-22"}

    def test_lone_night_is_not_a_two_night_stay(self):
        assert stay_starts(["2027-05-23"], 2) == set()

    def test_unsorted_and_duplicate_input(self):
        assert stay_starts(["2027-05-22", "2027-05-21", "2027-05-22"], 2) == {
            "2027-05-21",
        }

    def test_min_nights_below_one_counts_as_one(self):
        assert stay_starts(["2027-05-21"], 0) == {"2027-05-21"}


class TestNewStayNights:
    def test_first_poll_reports_nights_of_every_stay(self):
        current = ["2027-05-21", "2027-05-22", "2027-05-25"]
        assert new_stay_nights(current, [], 2) == ["2027-05-21", "2027-05-22"]

    def test_one_night_leftover_does_not_alert_a_two_night_watch(self):
        # Denny Creek: a 2-night weekend watch, only Sunday came free.
        assert new_stay_nights(["2027-05-23"], [], 2) == []

    def test_same_stay_does_not_re_alert(self):
        dates = ["2027-05-21", "2027-05-22"]
        assert new_stay_nights(dates, dates, 2) == []

    def test_night_that_completes_a_stay_alerts_the_whole_stay(self):
        previous = ["2027-05-21"]
        current = ["2027-05-21", "2027-05-22"]
        assert new_stay_nights(current, previous, 2) == ["2027-05-21", "2027-05-22"]

    def test_extended_run_reports_only_the_new_stay(self):
        previous = ["2027-05-21", "2027-05-22"]
        current = ["2027-05-20", "2027-05-21", "2027-05-22"]
        assert new_stay_nights(current, previous, 2) == ["2027-05-20", "2027-05-21"]

    def test_one_night_watch_matches_old_behaviour(self):
        previous = ["2027-05-21"]
        current = ["2027-05-21", "2027-05-23"]
        assert new_stay_nights(current, previous, 1) == ["2027-05-23"]


def _avail(dates: list[str]):
    return make_campground_availability(
        facility_id="232465",
        campsites={
            "1": make_campsite_availability(
                campsite_id="1", site="034", loop="A",
                dates_status={f"{d}T00:00:00.000Z": "Available" for d in dates},
            ),
        },
    )


def _client(dates: list[str]) -> RecGovClient:
    from unittest.mock import AsyncMock

    client = AsyncMock(spec=RecGovClient)
    client.get_availability_range.return_value = _avail(dates)
    return client


def _clear_cache(watch_db: WatchDB) -> None:
    watch_db._conn.execute("DELETE FROM availability_cache")


def _watch(watch_db: WatchDB, **kw) -> Watch:
    base = dict(
        facility_id="232465", name="Denny Creek",
        start_date="2027-05-21", end_date="2027-05-22", min_nights=2,
    )
    base.update(kw)
    return watch_db.add_watch(Watch(**base))


class TestPollWatchMinNights:
    @pytest.mark.asyncio
    async def test_one_night_leftover_does_not_alert(self, watch_db: WatchDB):
        watch = _watch(watch_db)
        result = await poll_watch(watch, _client(["2027-05-22"]), None, watch_db)
        assert result.changes == []
        assert result.current_available == 0

    @pytest.mark.asyncio
    async def test_full_stay_alerts(self, watch_db: WatchDB):
        watch = _watch(watch_db)
        result = await poll_watch(
            watch, _client(["2027-05-21", "2027-05-22"]), None, watch_db,
        )
        assert [c.new_dates for c in result.changes] == [["2027-05-21", "2027-05-22"]]
        assert result.current_available == 1

    @pytest.mark.asyncio
    async def test_leftover_then_completed_stay_alerts_once(self, watch_db: WatchDB):
        watch = _watch(watch_db)
        await poll_watch(watch, _client(["2027-05-22"]), None, watch_db)
        both = ["2027-05-21", "2027-05-22"]
        _clear_cache(watch_db)
        second = await poll_watch(watch, _client(both), None, watch_db)
        _clear_cache(watch_db)
        third = await poll_watch(watch, _client(both), None, watch_db)
        assert [c.new_dates for c in second.changes] == [both]
        assert third.changes == []

    @pytest.mark.asyncio
    async def test_days_of_week_runs_use_only_those_days(self, watch_db: WatchDB):
        # Fri 21 + Sat 22 with a Fri/Sat filter is a 2-night stay; Sat 22 +
        # Sun 23 isn't, because Sunday is filtered out.
        watch = _watch(
            watch_db, start_date="2027-05-21", end_date="2027-05-23",
            days_of_week=[4, 5],
        )
        result = await poll_watch(
            watch, _client(["2027-05-22", "2027-05-23"]), None, watch_db,
        )
        assert result.changes == []

    @pytest.mark.asyncio
    async def test_snapshot_from_before_deploy_does_not_flood(self, watch_db: WatchDB):
        # A snapshot saved by the old poller holds every available night. The
        # first poll after deploy must treat stays inside it as already seen.
        watch = _watch(watch_db)
        both = ["2027-05-21", "2027-05-22"]
        watch_db.save_snapshot(Snapshot(
            watch_id=watch.id, polled_at="2026-11-10T00:00:00",
            available_sites={"1": both},
        ))
        result = await poll_watch(watch, _client(both), None, watch_db)
        assert result.changes == []

    @pytest.mark.asyncio
    async def test_snapshot_keeps_every_available_night(self, watch_db: WatchDB):
        # The snapshot stays {site_id: [available nights]}, leftovers included,
        # so a later night that completes a stay can be diffed against it.
        watch = _watch(watch_db)
        await poll_watch(watch, _client(["2027-05-22"]), None, watch_db)
        snap = watch_db.get_latest_snapshot(watch.id)
        assert snap.available_sites == {"1": ["2027-05-22"]}
