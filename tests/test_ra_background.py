"""Oregon windows keep fetching after the search that wanted them stops waiting.

The search deadline used to cancel a park's fetch and throw its pages away, so
the next search for the same dates paid for the slowest parks again (43 s warm
in the slow-search RCA). Window fetches now belong to OregonWindows: searches
and the watch poller share one fetch per window, a window nobody waits on
finishes at background priority into the cache, within a cap.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.search.oregon_windows import OregonWindows, plan
from tests.test_ra_window_cache import A, avail, d, nights, row

CG = Campground(
    facility_id="402178", name="Fort Stevens", booking_system=BookingSystem.OR_STATE,
    state="OR", booking_url_slug="fort-stevens-state-park",
)


class GatedClient:
    """get_window blocks until its window's gate opens; records each call and
    whether it ran as background when the gate opened."""

    def __init__(self, open_all: bool = False) -> None:
        self.calls: list[tuple[date, date]] = []
        self.gates: dict[date, asyncio.Event] = {}
        self.background: dict[date, bool] = {}
        self.started: dict[date, asyncio.Event] = {}
        self.fail_on: set[date] = set()
        self.open_all = open_all

    def gate(self, arrival: date) -> asyncio.Event:
        return self.gates.setdefault(arrival, asyncio.Event())

    def was_started(self, arrival: date) -> asyncio.Event:
        return self.started.setdefault(arrival, asyncio.Event())

    async def get_window(self, park_id, slug, state, arrival, departure, *, background=None):
        self.calls.append((arrival, departure))
        self.was_started(arrival).set()
        if not self.open_all:
            await self.gate(arrival).wait()
        self.background[arrival] = bool(background and background())
        if arrival in self.fail_on:
            raise RuntimeError("boom")
        return avail(dict.fromkeys(nights(arrival, departure), A))


async def within(aw, seconds: float = 2.0):
    """Await with a ceiling, so a regression fails instead of hanging."""
    return await asyncio.wait_for(aw, seconds)


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def stored(watch_db, first: date, last: date) -> list[tuple[date, date]]:
    return sorted((a, b) for a, b, _, _ in watch_db.get_ra_windows(
        "402178", first, last, max_age_s=600,
    ))


class TestPlanWithPending:
    def test_a_pending_window_is_joined_not_fetched(self) -> None:
        p = plan(nights(d(5), d(20)), [], d(20), pending=[(d(5), d(18))])
        assert p.join == [(d(5), d(18))]
        assert p.fetch == [(d(19), d(20))]

    def test_a_stored_row_beats_a_pending_window(self) -> None:
        p = plan(nights(d(5), d(6)), [row(d(5), d(18))], d(6), pending=[(d(5), d(18))])
        assert p.join == []
        assert len(p.use) == 1


class TestSharedWindows:
    async def test_two_searches_share_one_fetch(self, watch_db) -> None:
        client = GatedClient()
        windows = OregonWindows(client, watch_db)
        a = asyncio.create_task(windows.park(CG, nights(d(5), d(18)), d(18)))
        b = asyncio.create_task(windows.park(CG, nights(d(6), d(18)), d(18)))
        await settle()
        client.gate(d(5)).set()
        got_a, got_b = await within(asyncio.gather(a, b))
        assert client.calls == [(d(5), d(18))]
        assert len(got_b.campsites["1"].availabilities) == 14

    async def test_a_cut_search_leaves_its_window_running_in_the_background(
        self, watch_db,
    ) -> None:
        client = GatedClient()
        windows = OregonWindows(client, watch_db)
        search = asyncio.create_task(windows.park(CG, nights(d(5), d(18)), d(18)))
        await within(client.was_started(d(5)).wait())
        search.cancel()
        await within(asyncio.gather(search, return_exceptions=True))
        assert windows.is_pending("402178")

        client.gate(d(5)).set()
        await within(windows.idle())
        assert client.background[d(5)] is True
        assert stored(watch_db, d(5), d(18)) == [(d(5), d(18))]
        assert not windows.is_pending("402178")

    async def test_a_new_search_brings_a_background_window_forward(self, watch_db) -> None:
        client = GatedClient()
        windows = OregonWindows(client, watch_db)
        first = asyncio.create_task(windows.park(CG, [d(5)], d(18)))
        await within(client.was_started(d(5)).wait())
        first.cancel()
        await within(asyncio.gather(first, return_exceptions=True))

        second = asyncio.create_task(windows.park(CG, [d(5)], d(18)))
        await settle()
        client.gate(d(5)).set()
        await within(second)
        assert client.calls == [(d(5), d(18))]
        assert client.background[d(5)] is False

    async def test_a_failed_window_stores_nothing_and_reaches_its_waiter(
        self, watch_db,
    ) -> None:
        client = GatedClient(open_all=True)
        client.fail_on = {d(5)}
        with pytest.raises(RuntimeError):
            await within(OregonWindows(client, watch_db).park(CG, [d(5)], d(18)))
        assert stored(watch_db, d(5), d(18)) == []


class TestBackgroundBound:
    async def test_a_window_losing_its_last_waiter_over_the_cap_is_cancelled(
        self, watch_db,
    ) -> None:
        client = GatedClient()
        windows = OregonWindows(client, watch_db, max_background=0)
        search = asyncio.create_task(windows.park(CG, [d(5)], d(18)))
        await within(client.was_started(d(5)).wait())
        search.cancel()
        await within(asyncio.gather(search, return_exceptions=True))
        await within(windows.idle())
        assert not windows.is_pending("402178")
        assert stored(watch_db, d(5), d(18)) == []



class TestShutdown:
    async def test_aclose_cancels_background_windows(self, watch_db) -> None:
        client = GatedClient()
        windows = OregonWindows(client, watch_db)
        search = asyncio.create_task(windows.park(CG, [d(1)], d(14)))
        await within(client.was_started(d(1)).wait())
        search.cancel()
        await within(asyncio.gather(search, return_exceptions=True))

        await within(windows.aclose())

        assert not windows.is_pending("402178")
        assert stored(watch_db, d(1), d(14)) == []
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
