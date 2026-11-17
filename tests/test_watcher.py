"""Tests for the watch/diff engine (watcher.py)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.watcher import (
    AvailabilityChange,
    PollResult,
    poll_all,
    poll_watch,
)
from pnw_campsites.providers.recgov import RecGovClient
from tests.conftest import (
    make_campground_availability,
    make_campsite_availability,
)


def _watch(db: WatchDB, **kw) -> Watch:
    kw = {
        "facility_id": "232465",
        "name": "Test Camp",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        **kw,
    }
    return db.add_watch(Watch(**kw))


def _site(*dates: str, campsite_id: str = "123456", **kw):
    """A campsite that is Available on each ISO date given."""
    return make_campsite_availability(
        campsite_id=campsite_id,
        dates_status={f"{d}T00:00:00.000Z": "Available" for d in dates},
        **kw,
    )


def _availability(*sites):
    return make_campground_availability(facility_id="232465", campsites={s.campsite_id: s for s in sites})


def _client(*sites) -> AsyncMock:
    """A RecGov client mock whose availability range holds `sites`."""
    client = AsyncMock(spec=RecGovClient)
    client.get_availability_range.return_value = _availability(*sites)
    return client


class TestPollWatchFirstPoll:
    """Tests for poll_watch on first poll (no previous snapshot)."""

    async def test_first_poll_reports_all_available_as_changes(self, watch_db: WatchDB):
        """First poll reports all available sites as new changes."""
        watch = _watch(watch_db)
        client = _client(_site("2026-06-01", "2026-06-02"))

        result = await poll_watch(watch, client, None, watch_db)

        assert len(result.changes) == 1
        assert result.changes[0].site_id == "123456"
        assert result.changes[0].new_dates == ["2026-06-01", "2026-06-02"]
        assert result.current_available == 1
        assert result.error is None

        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert snapshot is not None
        assert snapshot.available_sites == {"123456": ["2026-06-01", "2026-06-02"]}

    async def test_first_poll_captures_all_available_sites(self, watch_db: WatchDB):
        """First poll captures all available sites."""
        watch = _watch(watch_db)
        client = _client(
            _site("2026-06-01", campsite_id="123", site="A001"),
            _site("2026-06-02", campsite_id="456", site="A002"),
        )

        result = await poll_watch(watch, client, None, watch_db)

        assert result.current_available == 2
        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert len(snapshot.available_sites) == 2


class TestPollWatchChangeDetection:
    """Tests for detecting newly available sites."""

    async def test_second_poll_detects_new_available_dates(self, watch_db: WatchDB):
        """Second poll detects newly available dates not in first snapshot."""
        watch = _watch(watch_db)
        client = _client(_site("2026-06-01", "2026-06-02"))

        result1 = await poll_watch(watch, client, None, watch_db)
        assert len(result1.changes) == 1
        assert result1.changes[0].new_dates == ["2026-06-01", "2026-06-02"]

        # Second poll: June 3 is new
        client.get_availability_range.return_value = _availability(
            _site("2026-06-01", "2026-06-02", "2026-06-03")
        )

        # Clear cache so second poll hits the mock client
        watch_db._conn.execute("DELETE FROM availability_cache")
        watch_db._conn.commit()

        result2 = await poll_watch(watch, client, None, watch_db)

        assert len(result2.changes) == 1
        change = result2.changes[0]
        assert change.site_id == "123456"
        assert change.site_name == "A001"
        assert change.loop == "Loop A"
        assert change.campsite_type == "STANDARD NONELECTRIC"
        assert change.new_dates == ["2026-06-03"]
        assert change.max_people == 6

    async def test_second_poll_same_availability_no_changes(self, watch_db: WatchDB):
        """Second poll with same availability reports no changes."""
        watch = _watch(watch_db)
        client = _client(_site("2026-06-01", "2026-06-02"))

        result1 = await poll_watch(watch, client, None, watch_db)
        assert len(result1.changes) == 1

        result2 = await poll_watch(watch, client, None, watch_db)
        assert result2.changes == []
        assert result2.current_available == 1


class TestPollWatchFiltering:
    """Tests for date and day-of-week filtering."""

    async def test_poll_respects_date_range_filter(self, watch_db: WatchDB):
        """Poll ignores available dates outside the watch date range."""
        watch = _watch(watch_db, start_date="2026-06-10", end_date="2026-06-20")
        client = _client(_site("2026-06-01", "2026-06-15", "2026-06-25"))

        await poll_watch(watch, client, None, watch_db)

        # Only June 15 is in range [10, 20]
        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert snapshot.available_sites == {"123456": ["2026-06-15"]}

    async def test_poll_respects_day_of_week_filter(self, watch_db: WatchDB):
        """Poll filters available dates by day-of-week."""
        # June 2026: 1=Mon(0), 4=Thu(3), 5=Fri(4), 6=Sat(5)
        watch = _watch(watch_db, days_of_week=[3, 4, 5])  # Thu, Fri, Sat
        client = _client(_site("2026-06-01", "2026-06-04", "2026-06-05", "2026-06-06"))

        await poll_watch(watch, client, None, watch_db)

        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert set(snapshot.available_sites["123456"]) == {
            "2026-06-04",
            "2026-06-05",
            "2026-06-06",
        }


class TestPollWatchErrorHandling:
    """Tests for error handling during poll."""

    async def test_poll_captures_client_error(self, watch_db: WatchDB):
        """Poll captures client errors and returns result.error set."""
        watch = _watch(watch_db)
        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.side_effect = Exception("API error")

        result = await poll_watch(watch, client, None, watch_db)

        assert result.error is not None
        assert "API error" in result.error
        assert result.changes == []
        assert result.current_available == 0

    async def test_poll_does_not_crash_on_missing_site_metadata(self, watch_db: WatchDB):
        """Poll gracefully handles sites with missing metadata."""
        watch = _watch(watch_db)
        client = _client(_site("2026-06-01", site="", loop="", campsite_type="", max_people=0))

        result = await poll_watch(watch, client, None, watch_db)

        assert result.error is None
        assert len(result.changes) == 1
        assert result.changes[0].loop == ""
        assert result.changes[0].campsite_type == ""
        assert result.changes[0].max_people == 0


class TestPollAll:
    """Tests for polling all enabled watches."""

    async def test_poll_all_with_no_watches(self, watch_db: WatchDB):
        """poll_all with zero watches returns empty list."""
        client = AsyncMock(spec=RecGovClient)

        results = await poll_all(client, None, watch_db, today=date(2026, 6, 1))

        assert results == []
        client.get_availability_range.assert_not_called()

    async def test_poll_all_ignores_disabled_watches(self, watch_db: WatchDB):
        """poll_all only polls watches with enabled=True."""
        _watch(watch_db, name="Enabled Camp", enabled=True)
        _watch(watch_db, facility_id="232466", name="Disabled Camp", enabled=False)
        client = _client(make_campsite_availability())

        results = await poll_all(client, None, watch_db, today=date(2026, 6, 1))

        assert len(results) == 1
        assert results[0].watch.facility_id == "232465"

    async def test_poll_all_polls_multiple_watches(self, watch_db: WatchDB):
        """poll_all polls all enabled watches and returns results."""
        _watch(watch_db, name="Camp 1")
        _watch(watch_db, facility_id="232466", name="Camp 2", start_date="2026-07-01", end_date="2026-07-31")
        client = _client(make_campsite_availability())

        results = await poll_all(client, None, watch_db, today=date(2026, 6, 1))

        assert len(results) == 2
        facility_ids = [r.watch.facility_id for r in results]
        assert "232465" in facility_ids
        assert "232466" in facility_ids


class TestPollResult:
    """Tests for PollResult dataclass."""

    def test_poll_result_has_changes_property(self):
        """PollResult.has_changes returns True when changes exist."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        result = PollResult(watch=watch)

        assert result.has_changes is False

        result.changes.append(
            AvailabilityChange(
                watch=watch,
                site_id="123",
                site_name="A001",
                loop="Loop A",
                campsite_type="STANDARD",
                new_dates=["2026-06-01"],
                max_people=6,
            )
        )

        assert result.has_changes is True
