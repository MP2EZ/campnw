"""Oregon availability is cached per ReserveAmerica window, looked up per night.

A search used to cache a park only after every window and page finished, under
the exact extent it fetched. A park cut by the deadline kept nothing, and a
search for Feb 6-19 couldn't use a fetch of Feb 5-18. Each finished window is
now its own row, and a search fetches only the nights no fresh row covers.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import pnw_campsites.providers.reserveamerica as ra
from pnw_campsites.monitor.db import Watch
from pnw_campsites.monitor.watcher import poll_watch
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    BookingSystem,
    Campground,
    CampgroundAvailability,
    CampsiteAvailability,
)
from pnw_campsites.search.engine import SearchEngine, SearchQuery
from pnw_campsites.search.oregon_windows import CachedWindow, OregonWindows, merge, plan
from tests.conftest import make_campground
from tests.test_provider_reserveamerica import _make_record, _make_redux_html

A = AvailabilityStatus.AVAILABLE
R = AvailabilityStatus.RESERVED
T0 = datetime(2027, 1, 10, 12, 0)


def d(day: int, month: int = 2) -> date:
    return date(2027, month, day)


def nights(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def avail(statuses: dict[date, AvailabilityStatus], site: str = "1", name: str = "A1"):
    return CampgroundAvailability(facility_id="402178", campsites={
        site: CampsiteAvailability(
            campsite_id=site, site=name, loop="A", campsite_type="STANDARD",
            type_of_use="Overnight", min_num_people=0, max_num_people=8,
            availabilities={f"{n.isoformat()}T00:00:00.000Z": s for n, s in statuses.items()},
        ),
    })


def row(arrival: date, departure: date, at: datetime = T0, **kw) -> CachedWindow:
    statuses = kw.pop("statuses", dict.fromkeys(nights(arrival, departure), A))
    return CachedWindow(arrival, departure, at, avail(statuses, **kw))


class TestPlan:
    def test_nothing_cached_fetches_the_cover(self) -> None:
        p = plan(nights(d(5), d(28)), [], d(28))
        assert p.use == []
        assert p.fetch == [(d(5), d(18)), (d(19), d(28))]

    def test_everything_cached_fetches_nothing(self) -> None:
        rows = [row(d(5), d(18)), row(d(19), d(28))]
        p = plan(nights(d(5), d(28)), rows, d(28))
        assert p.fetch == []
        assert p.use == rows

    def test_a_misaligned_row_still_answers_its_nights(self) -> None:
        """Feb 5-18 is cached and Feb 6-19 wanted: only Feb 19 is fetched."""
        p = plan(nights(d(6), d(19)), [row(d(5), d(18))], d(19))
        assert p.fetch == [(d(19), d(19))]
        assert len(p.use) == 1

    def test_a_gap_between_rows_fetches_only_the_gap(self) -> None:
        rows = [row(d(1), d(10)), row(d(20), d(28))]
        p = plan(nights(d(1), d(28)), rows, d(28))
        assert p.fetch == [(d(11), d(24))]
        assert p.use == rows

    def test_rows_off_the_requested_nights_are_not_used(self) -> None:
        p = plan([d(5), d(6)], [row(d(10), d(20))], d(6))
        assert p.use == []

    def test_the_newest_row_answers_a_night(self) -> None:
        old, new = row(d(1), d(14)), row(d(1), d(14), T0 + timedelta(minutes=5))
        assert plan([d(3)], [old, new], d(3)).use == [new]

    def test_no_nights_no_work(self) -> None:
        assert plan([], [row(d(1), d(14))], d(14)).use == []


class TestMerge:
    def test_sites_from_every_window_are_kept(self) -> None:
        got = merge("402178", [
            row(d(1), d(1), statuses={d(1): A}, site="1"),
            row(d(2), d(2), statuses={d(2): A}, site="2"),
        ])
        assert set(got.campsites) == {"1", "2"}

    def test_dates_from_every_window_are_joined(self) -> None:
        got = merge("402178", [row(d(1), d(1)), row(d(2), d(2))])
        assert sorted(got.campsites["1"].availabilities) == [
            "2027-02-01T00:00:00.000Z", "2027-02-02T00:00:00.000Z",
        ]

    def test_the_newer_window_wins_an_overlapping_night(self) -> None:
        older = row(d(1), d(2), T0, statuses={d(1): A, d(2): A})
        newer = row(d(2), d(3), T0 + timedelta(minutes=1), statuses={d(2): R, d(3): R})
        for order in ([older, newer], [newer, older]):
            got = merge("402178", order).campsites["1"].availabilities
            assert got["2027-02-02T00:00:00.000Z"] == R
            assert got["2027-02-01T00:00:00.000Z"] == A

    def test_site_details_come_from_the_newer_window(self) -> None:
        older = row(d(1), d(1), T0, name="old")
        newer = row(d(2), d(2), T0 + timedelta(minutes=1), name="new")
        assert merge("402178", [newer, older]).campsites["1"].site == "new"

    def test_merging_leaves_the_rows_untouched(self) -> None:
        a, b = row(d(1), d(1)), row(d(2), d(2))
        merge("402178", [a, b])
        assert list(a.availability.campsites["1"].availabilities) == ["2027-02-01T00:00:00.000Z"]

    def test_nothing_to_merge(self) -> None:
        assert merge("402178", []).campsites == {}


class TestWindowStore:
    def test_rows_overlapping_the_nights_come_back(self, watch_db) -> None:
        watch_db.put_ra_window("402178", d(5), d(18), "{}", T0)
        watch_db.put_ra_window("402178", d(19), d(28), "{}", T0)
        watch_db.put_ra_window("999", d(5), d(18), "{}", T0)
        got = watch_db.get_ra_windows("402178", d(17), d(20), max_age_s=600, now=T0)
        assert sorted((a, b) for a, b, _, _ in got) == [(d(5), d(18)), (d(19), d(28))]
        assert watch_db.get_ra_windows("402178", d(1), d(4), max_age_s=600, now=T0) == []

    def test_stale_rows_are_misses(self, watch_db) -> None:
        watch_db.put_ra_window("402178", d(5), d(18), "{}", T0)
        later = T0 + timedelta(seconds=601)
        assert watch_db.get_ra_windows("402178", d(5), d(5), max_age_s=600, now=later) == []

    def test_a_refetch_replaces_the_row(self, watch_db) -> None:
        watch_db.put_ra_window("402178", d(5), d(18), "old", T0)
        watch_db.put_ra_window("402178", d(5), d(18), "new", T0 + timedelta(minutes=1))
        got = watch_db.get_ra_windows("402178", d(5), d(5), max_age_s=600, now=T0)
        assert [p for *_, p in got] == ["new"]

    def test_prune_drops_only_stale_rows(self, watch_db) -> None:
        watch_db.put_ra_window("402178", d(5), d(18), "{}", T0)
        watch_db.put_ra_window("402178", d(19), d(28), "{}", T0 + timedelta(minutes=20))
        assert watch_db.prune_ra_windows(600, now=T0 + timedelta(minutes=21)) == 1


class TestProviderWindow:
    async def test_one_window_fetches_every_page(self, monkeypatch) -> None:
        monkeypatch.setattr(ra, "_PAGE_SIZE", 1)
        client = ReserveAmericaClient()
        client._limiter.interval = 0
        client._session = MagicMock()
        records = [_make_record(site_id=i) for i in range(3)]
        client._session.get.side_effect = lambda url, params, timeout: MagicMock(
            status_code=200,
            text=_make_redux_html([records[params.get("pageNumber", 0)]], len(records)),
        )

        got = await client.get_window("402178", "park", "OR", d(5), d(18))

        assert client._session.get.call_count == 3
        assert set(got.campsites) == {"0", "1", "2"}
        sent = client._session.get.call_args_list[0].kwargs["params"]
        assert (sent["arrivalDate"], sent["departureDate"]) == ("2027-02-05", "2027-02-18")


CG = Campground(
    facility_id="402178", name="Fort Stevens", booking_system=BookingSystem.OR_STATE,
    state="OR", booking_url_slug="fort-stevens-state-park",
)


class FakeClient:
    """get_window returns a site available every night of the window."""

    def __init__(self) -> None:
        self.windows: list[tuple[date, date]] = []
        self.fail_on: date | None = None

    async def get_window(self, park_id, slug, state, arrival, departure):
        assert (park_id, slug, state) == ("402178", "fort-stevens-state-park", "OR")
        if arrival == self.fail_on:
            raise RuntimeError("boom")
        self.windows.append((arrival, departure))
        return avail(dict.fromkeys(nights(arrival, departure), A))


class TestOregonWindows:
    async def test_a_park_is_assembled_and_each_window_is_stored(self, watch_db) -> None:
        client = FakeClient()
        got = await OregonWindows(client, watch_db).park(CG, nights(d(5), d(28)), d(28))
        assert client.windows == [(d(5), d(18)), (d(19), d(28))]
        assert len(got.campsites["1"].availabilities) == 24
        assert len(watch_db.get_ra_windows("402178", d(5), d(28), max_age_s=600)) == 2

    async def test_a_repeat_fetches_nothing(self, watch_db) -> None:
        client = FakeClient()
        windows = OregonWindows(client, watch_db)
        await windows.park(CG, nights(d(5), d(28)), d(28))
        await windows.park(CG, nights(d(5), d(28)), d(28))
        assert len(client.windows) == 2

    async def test_an_overlapping_search_fetches_only_new_nights(self, watch_db) -> None:
        client = FakeClient()
        windows = OregonWindows(client, watch_db)
        await windows.park(CG, nights(d(5), d(18)), d(18))
        got = await windows.park(CG, nights(d(6), d(20)), d(20))
        assert client.windows == [(d(5), d(18)), (d(19), d(20))]
        assert len(got.campsites["1"].availabilities) == 16

    async def test_windows_done_before_a_failure_are_kept(self, watch_db) -> None:
        client = FakeClient()
        client.fail_on = d(19)
        with pytest.raises(RuntimeError):
            await OregonWindows(client, watch_db).park(CG, nights(d(5), d(28)), d(28))
        assert len(watch_db.get_ra_windows("402178", d(5), d(18), max_age_s=600)) == 1

    async def test_a_window_cut_mid_fetch_stores_nothing(self, watch_db) -> None:
        started = asyncio.Event()

        class Slow(FakeClient):
            async def get_window(self, *args):
                started.set()
                await asyncio.sleep(10)

        task = asyncio.create_task(OregonWindows(Slow(), watch_db).park(CG, [d(5)], d(5)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert watch_db.get_ra_windows("402178", d(5), d(5), max_age_s=600) == []


class TestEngineUsesWindows:
    def test_oregon_search_fetches_only_requested_windows(self, watch_db) -> None:
        client = FakeClient()
        eng = SearchEngine(registry=None, reserveamerica_client=client, watch_db=watch_db)
        query = SearchQuery(start_date=d(1, 3), end_date=d(31, 3), days_of_week={4, 5, 6})

        async def run():
            for _ in range(2):
                r = await eng._check_campground(CG, query.start_date, query.end_date, query)
                assert r.error is None
                assert r.total_available_sites == 1

        asyncio.run(run())
        assert client.windows == [(d(5, 3), d(18, 3)), (d(19, 3), d(31, 3))]

    def test_a_weekend_fetch_never_answers_an_every_night_search(self, watch_db) -> None:
        client = FakeClient()
        eng = SearchEngine(registry=None, reserveamerica_client=client, watch_db=watch_db)
        weekends = SearchQuery(start_date=d(1, 3), end_date=d(31, 3), days_of_week={4, 5, 6})
        every = SearchQuery(start_date=d(1, 3), end_date=d(31, 3))

        async def run():
            await eng._check_campground(CG, weekends.start_date, weekends.end_date, weekends)
            await eng._check_campground(CG, every.start_date, every.end_date, every)

        asyncio.run(run())
        # Mar 1-4 was never fetched for the weekends: one new window, starting Mar 1.
        assert client.windows[2:] == [(d(1, 3), d(14, 3))]


class TestWatchPoller:
    async def test_an_oregon_watch_polls_with_slug_and_state(self, watch_db, registry) -> None:
        """The poller called get_availability(facility_id, start, end), passing the
        dates as slug and state, so every Oregon watch poll raised TypeError."""
        registry.upsert(make_campground(
            facility_id="402178", name="Fort Stevens", state="OR",
            booking_system=BookingSystem.OR_STATE, booking_url_slug="fort-stevens-state-park",
        ))
        watch = watch_db.add_watch(Watch(
            facility_id="402178", name="Fort Stevens", start_date="2027-02-05",
            end_date="2027-02-07", booking_system=BookingSystem.OR_STATE.value,
        ))
        client = FakeClient()

        result = await poll_watch(
            watch, None, None, watch_db, registry=registry, reserveamerica=client,
        )

        assert result.error is None
        assert client.windows == [(d(5), d(7))]
        assert result.current_available == 1
