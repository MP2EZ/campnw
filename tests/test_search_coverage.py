"""Search coverage: campgrounds matched vs checked.

A search checks only the `max_campgrounds` closest matches, so "Checked 20
campgrounds" read as complete when 46 matched. `campgrounds_matched` is the
pool the cap selects from: everything past the registry, tag and distance
filters.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    SearchResults,
    StreamCoverageEvent,
)
from tests.conftest import make_campground, make_campground_availability

SEATTLE = (47.6, -122.3)


def _query(**overrides) -> SearchQuery:
    return SearchQuery(
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 30), **overrides,
    )


def _engine(registry) -> SearchEngine:
    """Providers report campgrounds with no sites at all."""
    empty = make_campground_availability(campsites={})
    recgov, wa = AsyncMock(), AsyncMock()
    recgov.get_availability_range = AsyncMock(return_value=empty)
    wa.get_availability = AsyncMock(return_value=empty)
    return SearchEngine(
        registry=registry, recgov_client=recgov, goingtocamp_client=wa,
    )


def _seed(registry, n: int, base: int, **overrides) -> None:
    for i in range(n):
        registry.upsert(make_campground(facility_id=str(base + i), **overrides))


class TestEngineCoverage:
    @pytest.mark.asyncio
    async def test_matched_is_the_pool_before_the_cap(self, registry) -> None:
        _seed(registry, 12, 1000)
        results = await _engine(registry).search(_query(max_campgrounds=5))
        assert (results.campgrounds_checked, results.campgrounds_matched) == (5, 12)

    @pytest.mark.asyncio
    async def test_matched_is_counted_after_distance_filtering(
        self, registry,
    ) -> None:
        """`registry_count` is pre-distance; matched must not be."""
        _seed(registry, 3, 2000, latitude=47.6, longitude=-122.3)
        _seed(registry, 4, 3000, latitude=42.0, longitude=-121.0, state="OR")

        results = await _engine(registry).search(_query(
            from_coords=SEATTLE, max_drive_minutes=120, max_campgrounds=2,
        ))

        assert (results.campgrounds_checked, results.campgrounds_matched) == (2, 3)

    @pytest.mark.asyncio
    async def test_uncapped_search_has_matched_equal_checked(
        self, registry,
    ) -> None:
        _seed(registry, 3, 4000)
        results = await _engine(registry).search(_query(max_campgrounds=20))
        assert results.campgrounds_matched == results.campgrounds_checked == 3

    @pytest.mark.asyncio
    async def test_cap_is_per_source_so_checked_can_exceed_the_limit(
        self, registry,
    ) -> None:
        """Without a source filter the cap applies per booking system."""
        _seed(registry, 3, 5000)
        for i in range(3):
            registry.upsert(make_campground(
                facility_id=str(-5000 - i), booking_system=BookingSystem.WA_STATE,
            ))

        results = await _engine(registry).search(_query(max_campgrounds=2))

        assert (results.campgrounds_checked, results.campgrounds_matched) == (4, 6)

    @pytest.mark.asyncio
    async def test_no_matches_reports_zero(self, registry) -> None:
        results = await _engine(registry).search(_query(name_like="nowhere"))
        assert (results.campgrounds_checked, results.campgrounds_matched) == (0, 0)


class TestStreamCoverage:
    @pytest.mark.asyncio
    async def test_stream_reports_matched_and_checked(self, registry) -> None:
        _seed(registry, 8, 6000)
        items = [i async for i in _engine(registry).search_stream(
            _query(max_campgrounds=3),
        )]
        coverage = [i for i in items if isinstance(i, StreamCoverageEvent)]
        assert [(c.campgrounds_matched, c.campgrounds_checked)
                for c in coverage] == [(8, 3)]

    @pytest.mark.asyncio
    async def test_stream_reports_coverage_when_nothing_matches(
        self, registry,
    ) -> None:
        items = [i async for i in _engine(registry).search_stream(
            _query(name_like="nowhere"),
        )]
        coverage = [i for i in items if isinstance(i, StreamCoverageEvent)]
        assert [(c.campgrounds_matched, c.campgrounds_checked)
                for c in coverage] == [(0, 0)]


class TestCoverageOverHttp:
    PARAMS = {"start_date": "2026-06-01", "end_date": "2026-06-30"}

    def test_search_endpoint_returns_campgrounds_matched(
        self, api_client, monkeypatch,
    ) -> None:
        from pnw_campsites.routes import search as search_routes

        class FakeEngine:
            async def search(self, query):
                return SearchResults(
                    query=query, campgrounds_checked=20, campgrounds_matched=46,
                )

        monkeypatch.setattr(search_routes, "get_engine", lambda: FakeEngine())
        data = api_client.get("/api/search", params=self.PARAMS).json()
        assert (data["campgrounds_checked"], data["campgrounds_matched"]) == (20, 46)

    def test_stream_carries_a_coverage_frame(
        self, api_client, monkeypatch,
    ) -> None:
        from pnw_campsites.routes import search as search_routes

        async def fake_stream(query):
            yield StreamCoverageEvent(campgrounds_matched=46, campgrounds_checked=20)

        class FakeEngine:
            search_stream = staticmethod(fake_stream)

        monkeypatch.setattr(search_routes, "get_engine", lambda: FakeEngine())
        resp = api_client.get("/api/search/stream", params=self.PARAMS)

        frames = [
            json.loads(line[len("data: "):]) for line in resp.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert {
            "type": "coverage", "campgrounds_matched": 46, "campgrounds_checked": 20,
        } in frames
