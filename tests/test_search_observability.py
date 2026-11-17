"""Slow searches were invisible (RCA 2026-11-15). The `search_timing` log
measured ~46 ms for every stream (the time to return the StreamingResponse),
PostHog had only time-to-[DONE], and ReserveAmerica requests weren't logged at
all. The stream now reports per-source completion and timeouts, in the logs
and in a `timing` frame the client sends to PostHog.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from pnw_campsites import api as api_module
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search import engine as engine_mod
from pnw_campsites.search.engine import SearchEngine, SearchQuery, StreamTimingEvent
from tests.conftest import make_campground_availability, make_campsite_availability
from tests.test_provider_reserveamerica import _make_record, _make_redux_html
from tests.test_search_timeouts import QUERY, _oregon, _seed


def _recgov():
    site = make_campsite_availability(dates_status={
        f"2026-07-0{d}T00:00:00.000Z": "Available" for d in (1, 2, 3)
    })
    client = AsyncMock()
    client.get_availability_range = AsyncMock(
        return_value=make_campground_availability(campsites={site.campsite_id: site}),
    )
    return client


async def _stream(registry, monkeypatch):
    monkeypatch.setattr(engine_mod, "PARK_TIMEOUT_S", 0.2)
    _seed(registry, 2, BookingSystem.OR_STATE, "or")
    _seed(registry, 3, BookingSystem.RECGOV, "rg")
    ra, _ = _oregon({"or1": 30})
    engine = SearchEngine(registry, recgov_client=_recgov(), reserveamerica_client=ra)
    return [ev async for ev in engine.search_stream(SearchQuery(**QUERY))]


async def test_stream_ends_with_per_source_timing(registry, monkeypatch) -> None:
    events = await _stream(registry, monkeypatch)

    timing = events[-1]
    assert isinstance(timing, StreamTimingEvent)
    assert timing.sources["recgov"]["checked"] == 3
    assert timing.sources["or_state"] == {
        "checked": 2, "done_ms": timing.sources["or_state"]["done_ms"],
        "timeouts": 0, "pending": 1, "errors": 0,
    }
    assert timing.sources["or_state"]["done_ms"] >= 200
    assert timing.sources["recgov"]["done_ms"] < timing.sources["or_state"]["done_ms"]
    assert timing.first_result_ms is not None
    assert timing.total_ms >= timing.sources["or_state"]["done_ms"]


async def test_stream_logs_one_summary_line(registry, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)
    await _stream(registry, monkeypatch)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("search_stream")]
    assert len(lines) == 1
    assert "recgov 3 in" in lines[0]
    assert "or_state 2 in" in lines[0] and "1 pending" in lines[0]


def test_route_sends_timing_and_records_the_real_duration(api_client, monkeypatch, caplog) -> None:
    from pnw_campsites.routes import search as search_routes

    class Engine:
        async def search_stream(self, query):
            yield StreamTimingEvent(
                sources={"recgov": {"checked": 1, "done_ms": 700, "timeouts": 0, "errors": 0}},
                first_result_ms=650, total_ms=91000,
            )

    monkeypatch.setattr(search_routes, "get_engine", lambda: Engine())
    api_module._search_timings.clear()
    caplog.set_level(logging.INFO)

    resp = api_client.get(
        "/api/search/stream", params={"start_date": "2027-06-04", "end_date": "2027-06-06"},
        headers={"Accept-Encoding": "identity"},
    )

    frames = [json.loads(line[6:]) for line in resp.text.splitlines()
              if line.startswith("data: {")]
    assert frames[-1] == {
        "type": "timing",
        "sources": {"recgov": {"checked": 1, "done_ms": 700, "timeouts": 0, "errors": 0}},
        "first_result_ms": 650, "total_ms": 91000,
    }
    assert list(api_module._search_timings) == [91000]
    assert not any("search_timing path=/api/search/stream" in r.getMessage()
                   for r in caplog.records)


async def test_reserveamerica_logs_requests_per_park(caplog) -> None:
    caplog.set_level(logging.INFO, logger="pnw_campsites.providers.reserveamerica")
    client = ReserveAmericaClient()
    client._limiter.interval = 0
    client._session = MagicMock()
    client._session.get.return_value = MagicMock(
        status_code=200, text=_make_redux_html([_make_record()], 1),
    )

    await client.get_availability("402178", "park", "OR", date(2027, 3, 1), date(2027, 3, 20))

    lines = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("ReserveAmerica 402178: 2 requests in") for m in lines), lines
