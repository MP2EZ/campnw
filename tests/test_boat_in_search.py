"""Boat-in campgrounds must never be presented as a plain drive.

A boat-in campground still has a coordinate, so the drive-time pipeline happily
computes "1h 03" for Blake Island. That number is the drive to the shoreline, not
to the campsite, so results flag ``boat_in`` and drop the drive time.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.registry.models import CampgroundAvailability
from pnw_campsites.routes.search import _format_result
from pnw_campsites.search.engine import (
    CampgroundResult,
    SearchEngine,
    SearchQuery,
)
from tests.conftest import make_campground, make_campsite_availability

SEATTLE = (47.6, -122.3)


def _available(facility_id, *args, **kwargs):
    return CampgroundAvailability(
        facility_id=facility_id,
        campsites={
            "1": make_campsite_availability(
                dates_status={
                    "2026-06-05T00:00:00.000Z": "Available",
                    "2026-06-06T00:00:00.000Z": "Available",
                },
            )
        },
    )


def _engine(registry) -> SearchEngine:
    recgov = AsyncMock()
    recgov.get_availability_range = AsyncMock(side_effect=_available)
    return SearchEngine(registry=registry, recgov_client=recgov)


def _query(**kw) -> SearchQuery:
    return SearchQuery(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        from_coords=SEATTLE,
        max_campgrounds=10,
        **kw,
    )


def _seed(registry):
    # A near drive-in, a boat-in that is nominally *closer*, and a far drive-in.
    registry.upsert(make_campground(
        facility_id="101", name="Drive-in 45", latitude=47.6, longitude=-121.5,
        tags=["forest"],
    ))
    registry.upsert(make_campground(
        facility_id="102", name="Island Boat-in", latitude=47.6, longitude=-122.28,
        tags=["boat-in", "beach"],
    ))
    registry.upsert(make_campground(
        facility_id="103", name="Drive-in far", latitude=47.6, longitude=-119.0,
        tags=["forest"],
    ))


class TestCampgroundResultFlag:
    def test_boat_in_true_when_tagged(self):
        cg = make_campground(tags=["beach", "boat-in"])
        assert CampgroundResult(campground=cg).boat_in is True

    def test_boat_in_false_otherwise(self):
        cg = make_campground(tags=["boat-launch", "walk-in"])
        assert CampgroundResult(campground=cg).boat_in is False


class TestEngine:
    @pytest.mark.asyncio
    async def test_boat_in_result_has_no_drive_time(self, registry):
        _seed(registry)
        results = await _engine(registry).search(_query())
        by_name = {r.campground.name: r for r in results.results}
        assert by_name["Island Boat-in"].estimated_drive_minutes is None
        assert by_name["Drive-in 45"].estimated_drive_minutes is not None

    @pytest.mark.asyncio
    async def test_boat_in_sorts_after_every_drive_in(self, registry):
        _seed(registry)
        results = await _engine(registry).search(_query())
        names = [r.campground.name for r in results.results]
        assert names == ["Drive-in 45", "Drive-in far", "Island Boat-in"]

    @pytest.mark.asyncio
    async def test_boat_in_stays_in_results_under_a_drive_limit(self, registry):
        _seed(registry)
        results = await _engine(registry).search(_query(max_drive_minutes=120))
        names = [r.campground.name for r in results.results]
        assert "Island Boat-in" in names
        assert "Drive-in far" not in names

    @pytest.mark.asyncio
    async def test_far_boat_in_still_excluded_by_drive_limit(self, registry):
        """The shoreline drive still bounds how far you travel to reach the water."""
        registry.upsert(make_campground(
            facility_id="104", name="Far Boat-in", latitude=47.6, longitude=-116.8,
            tags=["boat-in"],
        ))
        results = await _engine(registry).search(_query(max_drive_minutes=120))
        assert results.results == []

    @pytest.mark.asyncio
    async def test_stream_results_also_drop_drive_time(self, registry):
        _seed(registry)
        seen = {}
        async for item in _engine(registry).search_stream(_query()):
            if isinstance(item, CampgroundResult):
                seen[item.campground.name] = item
        assert seen["Island Boat-in"].estimated_drive_minutes is None
        assert seen["Drive-in 45"].estimated_drive_minutes is not None


class TestApiResponse:
    def test_boat_in_flag_true_and_no_drive_time(self):
        cg = make_campground(tags=["boat-in", "beach"])
        r = CampgroundResult(
            campground=cg, total_available_sites=1, estimated_drive_minutes=63,
        )
        out = _format_result(r, cg.booking_system)
        assert out.boat_in is True
        assert out.estimated_drive_minutes is None

    def test_regular_campground_keeps_drive_time_and_flag_false(self):
        cg = make_campground(tags=["lakeside"])
        r = CampgroundResult(
            campground=cg, total_available_sites=1, estimated_drive_minutes=63,
        )
        out = _format_result(r, cg.booking_system)
        assert out.boat_in is False
        assert out.estimated_drive_minutes == 63
