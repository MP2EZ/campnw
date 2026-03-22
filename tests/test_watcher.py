"""Tests for the watch/diff engine (watcher.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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


class TestPollWatchFirstPoll:
    """Tests for poll_watch on first poll (no previous snapshot)."""

    @pytest.mark.asyncio
    async def test_first_poll_reports_all_available_as_changes(
        self, watch_db: WatchDB
    ):
        """First poll reports all available sites as new changes."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        # Mock client returns availability
        client = AsyncMock(spec=RecGovClient)
        availability = make_campground_availability(
            facility_id="232465",
            campsites={
                "123456": make_campsite_availability(
                    campsite_id="123456",
                    site="A001",
                    loop="Loop A",
                    campsite_type="STANDARD NONELECTRIC",
                    max_people=6,
                    dates_status={
                        "2026-06-01T00:00:00.000Z": "Available",
                        "2026-06-02T00:00:00.000Z": "Available",
                    },
                ),
            },
        )
        client.get_availability_range.return_value = availability

        result = await poll_watch(watch, client, None, watch_db)

        # First poll reports all available as new
        assert len(result.changes) == 1
        assert result.changes[0].site_id == "123456"
        assert result.changes[0].new_dates == ["2026-06-01", "2026-06-02"]
        assert result.current_available == 1
        assert result.error is None

        # Verify snapshot was saved
        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert snapshot is not None
        assert snapshot.available_sites == {
            "123456": ["2026-06-01", "2026-06-02"]
        }

    @pytest.mark.asyncio
    async def test_first_poll_captures_all_available_sites(
        self, watch_db: WatchDB
    ):
        """First poll captures all available sites."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        client = AsyncMock(spec=RecGovClient)
        availability = make_campground_availability(
            facility_id="232465",
            campsites={
                "123": make_campsite_availability(
                    campsite_id="123",
                    site="A001",
                    dates_status={
                        "2026-06-01T00:00:00.000Z": "Available",
                    },
                ),
                "456": make_campsite_availability(
                    campsite_id="456",
                    site="A002",
                    dates_status={
                        "2026-06-02T00:00:00.000Z": "Available",
                    },
                ),
            },
        )
        client.get_availability_range.return_value = availability

        result = await poll_watch(watch, client, None, watch_db)

        assert result.current_available == 2
        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert len(snapshot.available_sites) == 2


class TestPollWatchChangeDetection:
    """Tests for detecting newly available sites."""

    @pytest.mark.asyncio
    async def test_second_poll_detects_new_available_dates(
        self, watch_db: WatchDB
    ):
        """Second poll detects newly available dates not in first snapshot."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        # First poll: June 1-2 available
        site1 = make_campsite_availability(
            campsite_id="123456",
            site="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            max_people=6,
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            },
        )
        availability1 = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site1},
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.return_value = availability1

        result1 = await poll_watch(watch, client, None, watch_db)
        # First poll reports all available as new
        assert len(result1.changes) == 1
        assert result1.changes[0].new_dates == ["2026-06-01", "2026-06-02"]

        # Second poll: June 1-3 available (June 3 is new)
        site2 = make_campsite_availability(
            campsite_id="123456",
            site="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            max_people=6,
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Available",
            },
        )
        availability2 = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site2},
        )
        client.get_availability_range.return_value = availability2

        # Clear cache so second poll hits the mock client
        watch_db.clear_expired_cache()
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

    @pytest.mark.asyncio
    async def test_second_poll_same_availability_no_changes(
        self, watch_db: WatchDB
    ):
        """Second poll with same availability reports no changes."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        site = make_campsite_availability(
            campsite_id="123456",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            },
        )
        availability = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site},
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.return_value = availability

        result1 = await poll_watch(watch, client, None, watch_db)
        # First poll reports all available as new
        assert len(result1.changes) == 1

        result2 = await poll_watch(watch, client, None, watch_db)
        # Second poll with same data has no new changes
        assert result2.changes == []
        assert result2.current_available == 1


class TestPollWatchFiltering:
    """Tests for date and day-of-week filtering."""

    @pytest.mark.asyncio
    async def test_poll_respects_date_range_filter(self, watch_db: WatchDB):
        """Poll ignores available dates outside the watch date range."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-10",
                end_date="2026-06-20",
            )
        )

        # Site has availability outside range: June 1, 15, 25
        site = make_campsite_availability(
            campsite_id="123456",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-15T00:00:00.000Z": "Available",
                "2026-06-25T00:00:00.000Z": "Available",
            },
        )
        availability = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site},
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.return_value = availability

        await poll_watch(watch, client, None, watch_db)

        # Only June 15 is in range [10, 20]
        snapshot = watch_db.get_latest_snapshot(watch.id)
        assert snapshot.available_sites == {"123456": ["2026-06-15"]}

    @pytest.mark.asyncio
    async def test_poll_respects_day_of_week_filter(self, watch_db: WatchDB):
        """Poll filters available dates by day-of-week."""
        # June 2026: 1=Mon(0), 2=Tue(1), 3=Wed(2), 4=Thu(3), 5=Fri(4), 6=Sat(5), 7=Sun(6)
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
                days_of_week=[3, 4, 5],  # Thu=3, Fri=4, Sat=5
            )
        )

        site = make_campsite_availability(
            campsite_id="123456",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",  # Mon (0)
                "2026-06-04T00:00:00.000Z": "Available",  # Thu (3)
                "2026-06-05T00:00:00.000Z": "Available",  # Fri (4)
                "2026-06-06T00:00:00.000Z": "Available",  # Sat (5)
            },
        )
        availability = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site},
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.return_value = availability

        await poll_watch(watch, client, None, watch_db)

        snapshot = watch_db.get_latest_snapshot(watch.id)
        # Only Thu, Fri, Sat are in the filter
        assert set(snapshot.available_sites["123456"]) == {
            "2026-06-04",
            "2026-06-05",
            "2026-06-06",
        }


class TestPollWatchErrorHandling:
    """Tests for error handling during poll."""

    @pytest.mark.asyncio
    async def test_poll_captures_client_error(self, watch_db: WatchDB):
        """Poll captures client errors and returns result.error set."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.side_effect = Exception("API error")

        result = await poll_watch(watch, client, None, watch_db)

        assert result.error is not None
        assert "API error" in result.error
        assert result.changes == []
        assert result.current_available == 0

    @pytest.mark.asyncio
    async def test_poll_does_not_crash_on_missing_site_metadata(
        self, watch_db: WatchDB
    ):
        """Poll gracefully handles sites with missing metadata."""
        watch = watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Test Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )

        # Create a site with minimal data
        site = make_campsite_availability(
            campsite_id="123456",
            site="",
            loop="",
            campsite_type="",
            max_people=0,
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
            },
        )
        availability = make_campground_availability(
            facility_id="232465",
            campsites={"123456": site},
        )

        client = AsyncMock(spec=RecGovClient)
        client.get_availability_range.return_value = availability

        result = await poll_watch(watch, client, None, watch_db)

        # Should not crash, first poll reports all available as new
        assert result.error is None
        assert len(result.changes) == 1
        # Missing fields should use defaults
        assert result.changes[0].loop == ""
        assert result.changes[0].campsite_type == ""
        assert result.changes[0].max_people == 0


class TestPollAll:
    """Tests for polling all enabled watches."""

    @pytest.mark.asyncio
    async def test_poll_all_with_no_watches(self, watch_db: WatchDB):
        """poll_all with zero watches returns empty list."""
        client = AsyncMock(spec=RecGovClient)

        results = await poll_all(client, None, watch_db)

        assert results == []
        client.get_availability_range.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_all_ignores_disabled_watches(self, watch_db: WatchDB):
        """poll_all only polls watches with enabled=True."""
        watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Enabled Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
                enabled=True,
            )
        )
        watch_db.add_watch(
            Watch(
                facility_id="232466",
                name="Disabled Camp",
                start_date="2026-06-01",
                end_date="2026-06-30",
                enabled=False,
            )
        )

        client = AsyncMock(spec=RecGovClient)
        availability = make_campground_availability(
            facility_id="232465",
            campsites={
                make_campsite_availability(campsite_id="123").campsite_id: (
                    make_campsite_availability()
                ),
            },
        )
        client.get_availability_range.return_value = availability

        results = await poll_all(client, None, watch_db)

        assert len(results) == 1
        assert results[0].watch.facility_id == "232465"

    @pytest.mark.asyncio
    async def test_poll_all_polls_multiple_watches(self, watch_db: WatchDB):
        """poll_all polls all enabled watches and returns results."""
        watch_db.add_watch(
            Watch(
                facility_id="232465",
                name="Camp 1",
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
        )
        watch_db.add_watch(
            Watch(
                facility_id="232466",
                name="Camp 2",
                start_date="2026-07-01",
                end_date="2026-07-31",
            )
        )

        client = AsyncMock(spec=RecGovClient)
        availability = make_campground_availability(
            facility_id="232465",
            campsites={
                make_campsite_availability(campsite_id="123").campsite_id: (
                    make_campsite_availability()
                ),
            },
        )
        client.get_availability_range.return_value = availability

        results = await poll_all(client, None, watch_db)

        assert len(results) == 2
        facility_ids = [r.watch.facility_id for r in results]
        assert "232465" in facility_ids
        assert "232466" in facility_ids


class TestAvailabilityChange:
    """Tests for AvailabilityChange dataclass."""

    def test_availability_change_stores_all_fields(self):
        """AvailabilityChange captures all site information."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            new_dates=["2026-06-01", "2026-06-02"],
            max_people=6,
        )

        assert change.watch == watch
        assert change.site_id == "123456"
        assert change.site_name == "A001"
        assert change.loop == "Loop A"
        assert change.campsite_type == "STANDARD NONELECTRIC"
        assert change.new_dates == ["2026-06-01", "2026-06-02"]
        assert change.max_people == 6


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

        change = AvailabilityChange(
            watch=watch,
            site_id="123",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
        )
        result.changes.append(change)

        assert result.has_changes is True

    def test_poll_result_tracks_error(self):
        """PollResult.error captures error messages."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        result = PollResult(watch=watch, error="Network timeout")

        assert result.error == "Network timeout"
        assert result.has_changes is False
