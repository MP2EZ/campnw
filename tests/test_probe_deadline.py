"""Zero-result date probes ran three more searches with no deadline after the
stream's own deadline (prod, 2026-11-15). A search for Fort Stevens timed out
at 60 s, then the probes re-fetched Fort Stevens on shifted dates for another
60 s, all timing out: two minutes to say "nothing found". And no byte reached
the client, not even headers, until the first park finished.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from unittest.mock import AsyncMock

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes import search as search_routes
from pnw_campsites.search import engine as engine_mod
from pnw_campsites.search.engine import SearchEngine, SearchQuery, StreamDiagnosisEvent
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)

START = date(2027, 7, 1)
END = date(2027, 7, 3)
ONE_WEEK_LATER = date(2027, 7, 8)


def _open_week_later():
    site = make_campsite_availability(dates_status={
        f"2027-07-{d:02d}T00:00:00.000Z": "Available" for d in (8, 9, 10)
    })
    return make_campground_availability(campsites={site.campsite_id: site})


def _recgov(slow_probes: bool):
    async def get_range(fid, start, end):
        if start == START:
            return make_campground_availability(campsites={})
        if start == ONE_WEEK_LATER:
            return _open_week_later()
        if slow_probes:
            await asyncio.sleep(30)
        return make_campground_availability(campsites={})

    client = AsyncMock()
    client.get_availability_range = AsyncMock(side_effect=get_range)
    return client


async def _diagnosis(engine: SearchEngine, query: SearchQuery) -> StreamDiagnosisEvent:
    events = [ev async for ev in engine.search_stream(query)]
    return next(ev for ev in events if isinstance(ev, StreamDiagnosisEvent))


async def test_probes_stop_at_their_budget_and_keep_what_finished(
    registry, monkeypatch,
) -> None:
    monkeypatch.setattr(engine_mod, "PROBE_DEADLINE_S", 0.2)
    registry.upsert(make_campground(facility_id="1", name="Slowpoke"))
    engine = SearchEngine(registry, recgov_client=_recgov(slow_probes=True))

    t0 = time.monotonic()
    diag = await _diagnosis(engine, SearchQuery(start_date=START, end_date=END))

    assert time.monotonic() - t0 < 5
    assert [s.start_date for s in diag.date_suggestions] == ["2027-07-08"]


async def test_probes_skip_oregon(registry) -> None:
    """Oregon probes can't finish in budget and would spend the 1 req/s shared
    with every other search."""
    registry.upsert(make_campground(
        facility_id="402178", name="Fort Stevens State Park",
        booking_system=BookingSystem.OR_STATE, state="OR", booking_url_slug="fort-stevens",
    ))
    ra = AsyncMock()
    ra.get_window = AsyncMock(return_value=make_campground_availability(campsites={}))
    engine = SearchEngine(registry, reserveamerica_client=ra)

    diag = await _diagnosis(
        engine, SearchQuery(start_date=START, end_date=END, name_like="fort stevens"),
    )

    assert ra.get_window.await_count == 1
    assert diag.date_suggestions == []


def test_stream_sends_a_byte_before_any_park_finishes(api_client, monkeypatch) -> None:

    class Engine:
        async def search_stream(self, query):
            await asyncio.sleep(0)
            return
            yield

    monkeypatch.setattr(search_routes, "get_engine", lambda: Engine())
    resp = api_client.get(
        "/api/search/stream",
        params={"start_date": "2027-06-04", "end_date": "2027-06-06"},
        headers={"Accept-Encoding": "identity"},
    )
    assert resp.text.startswith(": ")
    assert "data: [DONE]" in resp.text
