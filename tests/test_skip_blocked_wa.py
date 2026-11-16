"""GoingToCamp's WAF blocks prod's egress IP (2026-11-06). Every mixed search
still sent its 20 WA parks there, got 20 `waf_blocked`, and checked 20 fewer
campgrounds than it could have. A block now pauses WA for WAF_BACKOFF_S:
the rest of that search skips WA, and searches in the pause give WA's slots
to Recreation.gov. The pause ends on its own, so WA comes back when the
block lifts. The "WA couldn't be checked" warning still names every park
that wasn't checked.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from pnw_campsites.providers.errors import WAFBlockedError
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search import engine as engine_mod
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    StreamCoverageEvent,
    StreamWarningsEvent,
)
from tests.conftest import make_campground_availability
from tests.test_search_timeouts import QUERY, _seed


def _blocked_wa():
    async def get_availability(*_args, **_kwargs):
        await asyncio.sleep(0.01)
        raise WAFBlockedError("blocked")

    client = AsyncMock()
    client.get_availability = AsyncMock(side_effect=get_availability)
    return client


def _recgov():
    client = AsyncMock()
    client.get_availability_range = AsyncMock(return_value=make_campground_availability())
    return client


def _engine(registry, wa, recgov=None):
    return SearchEngine(registry, recgov_client=recgov or _recgov(), goingtocamp_client=wa)


async def _run(engine, **query):
    events = [ev async for ev in engine.search_stream(SearchQuery(**{**QUERY, **query}))]
    warnings = {
        (w.kind, w.source): w.count
        for ev in events if isinstance(ev, StreamWarningsEvent) for w in ev.warnings
    }
    coverage = next(ev for ev in events if isinstance(ev, StreamCoverageEvent))
    return warnings, coverage


async def test_a_block_stops_wa_for_the_rest_of_the_search(registry) -> None:
    _seed(registry, 10, BookingSystem.WA_STATE, "7")
    wa = _blocked_wa()

    warnings, _ = await _run(_engine(registry, wa), booking_system=BookingSystem.WA_STATE)

    assert wa.get_availability.await_count <= 3  # only the ones already in flight
    assert warnings[("waf_blocked", "wa_state")] == 10


async def test_searches_during_the_pause_give_wa_slots_to_recgov(registry) -> None:
    _seed(registry, 5, BookingSystem.WA_STATE, "7")
    _seed(registry, 30, BookingSystem.RECGOV, "rg")
    wa, recgov = _blocked_wa(), _recgov()
    engine = _engine(registry, wa, recgov)
    await _run(engine, max_campgrounds=5)
    wa.get_availability.reset_mock()
    recgov.get_availability_range.reset_mock()

    warnings, coverage = await _run(engine, max_campgrounds=5)

    assert wa.get_availability.await_count == 0
    assert recgov.get_availability_range.await_count == 10
    assert warnings[("waf_blocked", "wa_state")] == 5
    assert coverage.campgrounds_checked == 10


async def test_the_pause_ends_on_its_own(registry, monkeypatch) -> None:
    monkeypatch.setattr(engine_mod, "WAF_BACKOFF_S", 0.05)
    _seed(registry, 3, BookingSystem.WA_STATE, "7")
    wa = _blocked_wa()
    engine = _engine(registry, wa)
    await _run(engine)
    wa.get_availability.reset_mock()
    wa.get_availability.side_effect = None
    wa.get_availability.return_value = make_campground_availability()

    time.sleep(0.06)
    warnings, _ = await _run(engine)

    assert wa.get_availability.await_count == 3
    assert ("waf_blocked", "wa_state") not in warnings


async def test_other_wa_errors_dont_pause_wa(registry) -> None:
    _seed(registry, 4, BookingSystem.WA_STATE, "7")
    wa = AsyncMock()
    wa.get_availability = AsyncMock(side_effect=RuntimeError("boom"))
    engine = _engine(registry, wa)
    await _run(engine)
    await _run(engine)

    assert wa.get_availability.await_count == 8


async def test_non_streaming_search_reports_skipped_wa(registry) -> None:
    _seed(registry, 3, BookingSystem.WA_STATE, "7")
    _seed(registry, 6, BookingSystem.RECGOV, "rg")
    wa, recgov = _blocked_wa(), _recgov()
    engine = _engine(registry, wa, recgov)
    await _run(engine, max_campgrounds=3)
    wa.get_availability.reset_mock()
    recgov.get_availability_range.reset_mock()

    results = await engine.search(SearchQuery(**{**QUERY, "max_campgrounds": 3}))

    assert wa.get_availability.await_count == 0
    assert recgov.get_availability_range.await_count == 6

    assert {(w.kind, w.source): w.count for w in results.warnings}[
        ("waf_blocked", "wa_state")
    ] == 3
    assert results.campgrounds_checked == 6
