"""One slow park must not hold the search stream (Oregon stall, 2026-11-07).

On prod an Oregon-only search streamed five parks in 67 s, then sent nothing
for 96 s while the sixth park paged, and the connection closed with no
coverage or done frame. The UI stayed on "Checking campgrounds…".
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.search import warning_message
from pnw_campsites.search import engine as engine_mod
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    StreamCoverageEvent,
    StreamProgressEvent,
    StreamWarningsEvent,
)
from tests.conftest import make_campground, make_campground_availability

QUERY = dict(
    start_date=date(2026, 7, 1), end_date=date(2026, 7, 3), max_campgrounds=20,
)


def _seed(registry, n: int, system: BookingSystem, prefix: str) -> None:
    for i in range(n):
        registry.upsert(make_campground(
            facility_id=f"{prefix}{i}", name=f"{prefix} park {i}",
            booking_system=system, booking_url_slug="park", state="OR",
        ))


def _oregon(delay_for: dict[str, float], default: float = 0.0):
    """Fake ReserveAmerica client whose parks take the given seconds."""
    state = {"running": 0, "max_running": 0, "cancelled": 0}

    async def get_availability(park_id, *_args):
        state["running"] += 1
        state["max_running"] = max(state["max_running"], state["running"])
        try:
            await asyncio.sleep(delay_for.get(park_id, default))
        except asyncio.CancelledError:
            state["cancelled"] += 1
            raise
        finally:
            state["running"] -= 1
        return make_campground_availability(facility_id=park_id)

    client = AsyncMock()
    client.get_availability = AsyncMock(side_effect=get_availability)
    return client, state


async def _collect(engine: SearchEngine, query: SearchQuery) -> list:
    return [ev async for ev in engine.search_stream(query)]


def _results(events: list) -> list:
    return [
        ev.result if isinstance(ev, StreamProgressEvent) else ev
        for ev in events
        if isinstance(ev, StreamProgressEvent) or hasattr(ev, "campground")
    ]


async def test_a_slow_park_times_out_and_the_stream_finishes(
    registry, monkeypatch,
) -> None:
    monkeypatch.setattr(engine_mod, "PARK_TIMEOUT_S", 0.2)
    _seed(registry, 3, BookingSystem.OR_STATE, "or")
    ra, _ = _oregon({"or1": 30})
    engine = SearchEngine(registry, reserveamerica_client=ra)

    t0 = time.monotonic()
    events = await asyncio.wait_for(
        _collect(engine, SearchQuery(booking_system=BookingSystem.OR_STATE, **QUERY)),
        timeout=5,
    )

    assert time.monotonic() - t0 < 2
    errors = {r.campground.facility_id: r.error for r in _results(events)}
    assert errors == {"or0": None, "or1": "timeout", "or2": None}
    warnings = next(ev for ev in events if isinstance(ev, StreamWarningsEvent))
    assert [(w.kind, w.source, w.count) for w in warnings.warnings] == [
        ("timeout", "or_state", 1),
    ]


async def test_the_search_deadline_ends_the_stream_with_every_park_reported(
    registry, monkeypatch,
) -> None:
    monkeypatch.setattr(engine_mod, "SEARCH_DEADLINE_S", 0.5)
    _seed(registry, 12, BookingSystem.OR_STATE, "or")
    ra, state = _oregon({}, default=0.3)
    engine = SearchEngine(registry, reserveamerica_client=ra)

    t0 = time.monotonic()
    events = await asyncio.wait_for(
        _collect(engine, SearchQuery(booking_system=BookingSystem.OR_STATE, **QUERY)),
        timeout=5,
    )

    assert time.monotonic() - t0 < 1.5
    results = _results(events)
    assert len(results) == 12
    timed_out = [r for r in results if r.error == "timeout"]
    assert 0 < len(timed_out) < 12
    coverage = next(ev for ev in events if isinstance(ev, StreamCoverageEvent))
    assert coverage.campgrounds_checked == 12
    await asyncio.sleep(0)
    assert state["running"] == 0, "timed-out parks were left running"


async def test_closing_the_stream_cancels_unfinished_parks(registry) -> None:
    """A user who leaves mid-search must not keep spending Oregon's budget."""
    _seed(registry, 6, BookingSystem.OR_STATE, "or")
    ra, state = _oregon({"or0": 0.0}, default=30)
    engine = SearchEngine(registry, reserveamerica_client=ra)

    stream = engine.search_stream(
        SearchQuery(booking_system=BookingSystem.OR_STATE, **QUERY),
    )
    async for _ev in stream:
        break
    await stream.aclose()
    await asyncio.sleep(0)

    assert state["running"] == 0
    assert state["cancelled"] > 0


async def test_oregon_parks_run_two_at_a_time_without_blocking_others(
    registry,
) -> None:
    """Oregon requests share one app-wide 1 req/s limit. Eight parks in
    parallel each get an eighth of it and all finish last; two at a time
    finish in drive order. Other sources keep the full fan-out."""
    _seed(registry, 6, BookingSystem.OR_STATE, "or")
    _seed(registry, 6, BookingSystem.RECGOV, "rg")
    ra, ra_state = _oregon({}, default=0.1)
    recgov = AsyncMock()

    async def recgov_avail(facility_id, *_args):
        await asyncio.sleep(0.05)
        return make_campground_availability(facility_id=facility_id)

    recgov.get_availability_range = AsyncMock(side_effect=recgov_avail)
    engine = SearchEngine(registry, recgov, reserveamerica_client=ra)

    t0 = time.monotonic()
    rg_done: list[float] = []
    async for ev in engine.search_stream(SearchQuery(**QUERY)):
        r = ev.result if isinstance(ev, StreamProgressEvent) else ev
        if getattr(r, "campground", None) and r.campground.facility_id.startswith("rg"):
            rg_done.append(time.monotonic() - t0)

    assert ra_state["max_running"] == 2
    assert len(rg_done) == 6
    assert max(rg_done) < 0.3, "Recreation.gov parks queued behind Oregon"


@pytest.mark.parametrize("source,label", [
    ("or_state", "Oregon State Parks"), ("nope", None),
])
def test_timeout_warning_copy(source: str, label: str | None) -> None:
    msg = warning_message("timeout", source)
    assert "too long" in msg
    if label:
        assert label in msg
