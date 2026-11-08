"""Watch poller: provider dispatch, past-dated watches, failure containment.

Prod 2026-11-06: WA watches were polled against the rec.gov URL (400 every
cycle) and watches whose dates had ended kept being polled.
"""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.monitor.db import Watch
from pnw_campsites.monitor.notify import format_poll_result
from pnw_campsites.monitor.watcher import (
    heal_booking_systems,
    poll_all,
    resolve_booking_system,
)
from pnw_campsites.providers.errors import WAFBlockedError
from pnw_campsites.registry.models import BookingSystem, CampgroundAvailability
from tests.conftest import make_campground

WA_ID = "-2147483624"  # GoingToCamp resourceLocationId
OR_ID = "409402"  # ReserveAmerica park id
RG_ID = "232465"
TODAY = date(2026, 11, 7)


@pytest.fixture
def seeded(registry):
    registry.upsert(make_campground(facility_id=RG_ID))
    registry.upsert(make_campground(
        facility_id=WA_ID, name="Deception Pass",
        booking_system=BookingSystem.WA_STATE,
    ))
    registry.upsert(make_campground(
        facility_id=OR_ID, name="Ainsworth", state="OR",
        booking_system=BookingSystem.OR_STATE, booking_url_slug="ainsworth",
    ))
    return registry


def _avail(fid: str) -> CampgroundAvailability:
    return CampgroundAvailability(facility_id=fid, campsites={})


def _clients():
    recgov, gtc, ra = AsyncMock(), AsyncMock(), AsyncMock()
    recgov.get_availability_range.side_effect = lambda f, s, e: _avail(f)
    gtc.get_availability.side_effect = lambda f, s, e: _avail(str(f))
    ra.get_availability.side_effect = lambda f, s, e: _avail(f)
    return recgov, gtc, ra


def _watch(fid: str, start="2027-06-01", end="2027-06-30", **kw) -> Watch:
    return Watch(facility_id=fid, name=fid, start_date=start, end_date=end, **kw)


@pytest.mark.parametrize("fid, stored, want", [
    (WA_ID, "recgov", "wa_state"),
    (OR_ID, "recgov", "or_state"),
    (RG_ID, "recgov", "recgov"),
    ("-2147480000", "recgov", "wa_state"),  # WA park missing from the registry
    ("999999", "recgov", "recgov"),
    (RG_ID, "or_state", "or_state"),  # a non-default value was set on purpose
])
def test_resolve_booking_system(seeded, fid, stored, want):
    assert resolve_booking_system(fid, stored, seeded) == want


class TestDispatch:
    @pytest.mark.asyncio
    async def test_wa_and_or_watches_reach_their_providers(self, watch_db, seeded):
        """Rows saved with the 'recgov' default (prod watches 7 and 9)."""
        wa = watch_db.add_watch(_watch(WA_ID))
        orw = watch_db.add_watch(_watch(OR_ID))
        watch_db.add_watch(_watch(RG_ID))
        recgov, gtc, ra = _clients()

        results = await poll_all(
            recgov, gtc, watch_db, seeded, reserveamerica=ra, today=TODAY,
        )

        assert [r.error for r in results] == [None, None, None]
        gtc.get_availability.assert_called_once_with(
            int(WA_ID), date(2027, 6, 1), date(2027, 6, 30),
        )
        assert ra.get_availability.call_args.args[0] == OR_ID
        assert [c.args[0] for c in recgov.get_availability_range.call_args_list] == [RG_ID]
        assert watch_db.get_watch(wa.id).booking_system == "wa_state"
        assert watch_db.get_watch(orw.id).booking_system == "or_state"

    @pytest.mark.asyncio
    async def test_template_expansion_keeps_each_parks_provider(self, watch_db, seeded):
        watch_db.add_watch(_watch(
            "", watch_type="template", search_params='{"state": "OR"}',
        ))
        recgov, gtc, ra = _clients()

        await poll_all(recgov, gtc, watch_db, seeded, reserveamerica=ra, today=TODAY)

        assert ra.get_availability.call_args.args[0] == OR_ID
        recgov.get_availability_range.assert_not_called()

    def test_startup_heal_covers_disabled_watches_and_is_idempotent(
        self, watch_db, seeded,
    ):
        paused = watch_db.add_watch(_watch(WA_ID, enabled=False))
        watch_db.add_watch(_watch(RG_ID))

        assert heal_booking_systems(watch_db, seeded) == 1
        assert heal_booking_systems(watch_db, seeded) == 0
        assert watch_db.get_watch(paused.id).booking_system == "wa_state"

    def test_create_route_stores_wa_source(self, api_client):
        from pnw_campsites import api as api_module

        api_module._registry.booking_systems_for.return_value = [
            BookingSystem.WA_STATE,
        ]
        resp = api_client.post("/api/watches", json={
            "facility_id": WA_ID, "name": "Deception Pass",
            "start_date": "2027-06-01", "end_date": "2027-06-30",
        })
        assert resp.status_code == 200
        saved = api_module._watch_db.get_watch(resp.json()["id"])
        assert saved.booking_system == "wa_state"


class TestBookingLinks:
    @pytest.mark.asyncio
    async def test_notifications_link_to_the_watchs_own_site(self, watch_db, seeded):
        watch_db.add_watch(_watch(WA_ID))
        watch_db.add_watch(_watch(OR_ID))
        recgov, gtc, ra = _clients()

        results = await poll_all(
            recgov, gtc, watch_db, seeded, reserveamerica=ra, today=TODAY,
        )
        urls = {r.watch.facility_id: format_poll_result(r) for r in results}

        assert "washington.goingtocamp.com" in urls[WA_ID]
        assert "reserveamerica.com/explore/ainsworth/OR/409402" in urls[OR_ID]
        assert not any("recreation.gov" in u for u in urls.values())


class TestPastDatedWatches:
    @pytest.mark.asyncio
    async def test_ended_watch_is_skipped_but_kept(self, watch_db, seeded):
        ended = watch_db.add_watch(_watch(RG_ID, "2026-10-01", "2026-11-06"))
        recgov, gtc, ra = _clients()

        results = await poll_all(recgov, gtc, watch_db, seeded, today=TODAY)

        assert results == []
        recgov.get_availability_range.assert_not_called()
        kept = watch_db.get_watch(ended.id)
        assert kept is not None and kept.enabled

    @pytest.mark.asyncio
    async def test_partly_passed_watch_polls_from_today(self, watch_db, seeded):
        watch_db.add_watch(_watch(RG_ID, "2026-11-01", "2026-11-07"))
        recgov, gtc, ra = _clients()

        results = await poll_all(recgov, gtc, watch_db, seeded, today=TODAY)

        assert len(results) == 1
        recgov.get_availability_range.assert_called_once_with(RG_ID, TODAY, TODAY)

    def test_api_marks_ended_watch_expired(self, api_client, monkeypatch):
        from pnw_campsites.monitor import watcher

        monkeypatch.setattr(watcher, "pacific_today", lambda: TODAY)
        for start, end in [("2026-10-01", "2026-11-06"), ("2026-11-01", "2026-11-07")]:
            api_client.post("/api/watches", json={
                "facility_id": RG_ID, "name": "x",
                "start_date": start, "end_date": end,
            })
        listed = api_client.get("/api/watches").json()
        assert sorted(w["expired"] for w in listed) == [False, True]


class TestFailureContainment:
    @pytest.mark.asyncio
    async def test_waf_block_is_one_request_and_one_warning_per_cycle(
        self, watch_db, seeded, caplog,
    ):
        for i in range(3):
            watch_db.add_watch(_watch(WA_ID, start=f"2027-06-0{i + 1}"))
        watch_db.add_watch(_watch(RG_ID))
        recgov, gtc, ra = _clients()
        gtc.get_availability.side_effect = WAFBlockedError("blocked")

        with caplog.at_level(logging.WARNING, logger="pnw_campsites"):
            results = await poll_all(recgov, gtc, watch_db, seeded, today=TODAY)

        by_fid = {}
        for r in results:
            by_fid.setdefault(r.watch.facility_id, []).append(r.error)
        assert by_fid[RG_ID] == [None]
        assert len(by_fid[WA_ID]) == 3 and all(by_fid[WA_ID])
        assert gtc.get_availability.call_count == 1  # no retries, no per-watch refetch
        records = [r for r in caplog.records if r.name.startswith("pnw_campsites")]
        assert all(r.levelno == logging.WARNING for r in records)
        assert len(records) == 1
        assert "wa_state" in records[0].getMessage()
