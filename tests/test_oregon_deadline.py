"""Oregon gets its own, shorter deadline, and cut parks report "pending".

An Oregon-inclusive month search needs 110-170 ReserveAmerica requests at
1 req/s, so every one ran to the 90 s search deadline before the user saw a
verdict. Oregon parks are now cut at OREGON_DEADLINE_S. A cut park whose
windows went to the background reports "pending" ("still checking"), and
"Check again" picks it up from the cache. A park the background couldn't take
is still a "timeout".
"""

from __future__ import annotations

import asyncio

import pytest

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.search import warning_message
from pnw_campsites.search import engine as engine_mod
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    StreamDiagnosisEvent,
    StreamTimingEvent,
    StreamWarningsEvent,
)
from tests.test_search_observability import _recgov
from tests.test_search_timeouts import QUERY, _collect, _oregon, _results, _seed


def test_the_oregon_deadline_is_30s() -> None:
    assert engine_mod.OREGON_DEADLINE_S == 30.0


async def _run(registry, monkeypatch, *, max_background: int | None = None, recgov=True):
    monkeypatch.setattr(engine_mod, "OREGON_DEADLINE_S", 0.2)
    _seed(registry, 4, BookingSystem.OR_STATE, "or")
    if recgov:
        _seed(registry, 2, BookingSystem.RECGOV, "rg")
    ra, state = _oregon({"or0": 0.0}, default=5)
    engine = SearchEngine(registry, recgov_client=_recgov(), reserveamerica_client=ra)
    if max_background is not None:
        engine.oregon._max_background = max_background
    events = await asyncio.wait_for(
        _collect(engine, SearchQuery(**QUERY)), timeout=3,
    )
    await engine.oregon.aclose()
    return engine, events


async def test_cut_oregon_parks_are_pending_and_the_rest_finish(registry, monkeypatch) -> None:
    _, events = await _run(registry, monkeypatch)

    by_id = {r.campground.facility_id: r for r in _results(events)}
    assert by_id["or0"].error is None
    assert [by_id[f"or{i}"].error for i in (1, 2, 3)] == ["pending"] * 3
    assert by_id["rg0"].error is None and by_id["rg1"].error is None

    warnings = next(ev for ev in events if isinstance(ev, StreamWarningsEvent)).warnings
    assert [(w.kind, w.source, w.count) for w in warnings] == [("pending", "or_state", 3)]

    timing = next(ev for ev in events if isinstance(ev, StreamTimingEvent))
    assert timing.sources["or_state"]["pending"] == 3
    assert timing.sources["or_state"]["timeouts"] == 0
    assert timing.total_ms < 1000


async def test_parks_the_background_cannot_take_are_timeouts(registry, monkeypatch) -> None:
    _, events = await _run(registry, monkeypatch, max_background=0)

    errors = sorted(r.error or "" for r in _results(events) if r.campground.facility_id != "or0")
    assert errors == ["", "", "timeout", "timeout", "timeout"]


async def test_no_date_probes_while_oregon_is_still_checking(registry, monkeypatch) -> None:
    probes = []

    async def probe(self, query):
        probes.append(query)
        return []

    monkeypatch.setattr(SearchEngine, "_suggest_alternative_dates", probe)
    monkeypatch.setattr(engine_mod, "OREGON_DEADLINE_S", 0.2)
    _seed(registry, 3, BookingSystem.OR_STATE, "or")
    ra, _ = _oregon({}, default=5)
    engine = SearchEngine(registry, reserveamerica_client=ra)

    events = await asyncio.wait_for(_collect(engine, SearchQuery(**QUERY)), timeout=3)
    await engine.oregon.aclose()

    assert any(isinstance(ev, StreamDiagnosisEvent) for ev in events)
    assert probes == []


@pytest.mark.parametrize("count,expected", [
    (1, "Still checking 1 Oregon State Parks campground."),
    (3, "Still checking 3 Oregon State Parks campgrounds."),
])
def test_pending_warning_copy(count: int, expected: str) -> None:
    msg = warning_message("pending", "or_state", count)
    assert msg.startswith(expected)
    assert "Check again" in msg
