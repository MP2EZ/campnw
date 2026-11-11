"""Watch site filters (v1.48 P3c): party, rig and site type, as the search's `who`."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.watcher import poll_all, poll_watch
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.models import SiteFit
from tests.conftest import make_campground_availability, make_campsite_availability
from tests.test_site_fit import FORT_EBEY_7, FORT_EBEY_MAIN

JUNE_1 = "2027-06-01T00:00:00.000Z"


# ---------------------------------------------------------------------------
# Storage and migration
# ---------------------------------------------------------------------------


class TestWatchStorage:
    def test_filters_round_trip(self, watch_db: WatchDB):
        saved = watch_db.add_watch(Watch(
            facility_id="232465", start_date="2027-06-05", end_date="2027-06-06",
            min_people=4, equipment="trailer", rig_length=30, site_types=["hookups"],
        ))
        got = watch_db.get_watch(saved.id)
        assert (got.min_people, got.equipment, got.rig_length, got.site_types) == (
            4, "trailer", 30, ["hookups"],
        )
        assert got.has_site_filters

    def test_unfiltered_watch_reads_back_as_none(self, watch_db: WatchDB):
        saved = watch_db.add_watch(
            Watch(facility_id="232465", start_date="2027-06-05", end_date="2027-06-06"),
        )
        got = watch_db.get_watch(saved.id)
        assert (got.min_people, got.equipment, got.rig_length, got.site_types) == (
            None, None, None, None,
        )
        assert not got.has_site_filters

    def test_migration_adds_columns_to_existing_rows_idempotently(self, tmp_path):
        path = tmp_path / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                min_nights INTEGER DEFAULT 1, days_of_week TEXT,
                notify_topic TEXT DEFAULT '', session_token TEXT DEFAULT '',
                user_id INTEGER, enabled INTEGER DEFAULT 1, created_at TEXT,
                booking_system TEXT NOT NULL DEFAULT 'recgov'
            );
            INSERT INTO watches (facility_id, name, start_date, end_date)
            VALUES ('232465', 'Old', '2027-06-01', '2026-06-30');
        """)
        conn.commit()
        conn.close()

        for _ in range(2):  # a second open must not fail or change anything
            with WatchDB(path) as db:
                (old,) = db.list_watches(enabled_only=False)
                assert old.name == "Old"
                assert not old.has_site_filters


# ---------------------------------------------------------------------------
# Poller
# ---------------------------------------------------------------------------


def _client(campsites: dict) -> AsyncMock:
    client = AsyncMock(spec=RecGovClient)
    client.get_availability_range.return_value = make_campground_availability(
        facility_id="232465", campsites=campsites,
    )
    return client


def _site(site_id: str, **kw):
    return make_campsite_availability(
        campsite_id=site_id, site=site_id, dates_status={JUNE_1: "Available"}, **kw,
    )


def _watch(db: WatchDB, **filters) -> Watch:
    return db.add_watch(Watch(
        facility_id="232465", name="Camp", start_date="2027-06-01", end_date="2027-06-02",
        **filters,
    ))


async def _alerted(db: WatchDB, watch: Watch, campsites: dict) -> set[str]:
    result = await poll_watch(watch, _client(campsites), None, db)
    assert result.error is None
    return {c.site_id for c in result.changes}


class TestPollerFilters:
    @pytest.mark.asyncio
    async def test_unfiltered_watch_alerts_on_every_site(self, watch_db: WatchDB):
        sites = {
            "small": _site("small", max_people=2),
            "rv": _site("rv", campsite_type="RV NONELECTRIC"),
        }
        assert await _alerted(watch_db, _watch(watch_db), sites) == {"small", "rv"}

    @pytest.mark.asyncio
    async def test_party_size_drops_sites_known_too_small(self, watch_db: WatchDB):
        placeholder = _site("placeholder", max_people=2)
        placeholder.max_people_known = False
        sites = {
            "small": _site("small", max_people=2),
            "big": _site("big", max_people=6),
            "placeholder": placeholder,
        }
        watch = _watch(watch_db, min_people=4)
        assert await _alerted(watch_db, watch, sites) == {"big", "placeholder"}

    @pytest.mark.asyncio
    async def test_equipment_uses_the_search_fit_rules(self, watch_db: WatchDB):
        short_rv = _site("short")
        short_rv.fit = SiteFit(fits_rv=True, max_rv_ft=25)
        sites = {
            "tent": _site("tent", campsite_type="TENT ONLY NONELECTRIC"),
            "short": short_rv,
            "rv": _site("rv", campsite_type="RV ELECTRIC"),  # no stated length
            "standard": _site("standard", campsite_type="STANDARD NONELECTRIC"),  # unknown
        }
        watch = _watch(watch_db, equipment="trailer", rig_length=30)
        assert await _alerted(watch_db, watch, sites) == {"rv", "standard"}

    @pytest.mark.asyncio
    async def test_site_types_keep_unknown_hookups(self, watch_db: WatchDB):
        sites = {
            "electric": _site("electric", campsite_type="STANDARD ELECTRIC"),
            "plain": _site("plain", campsite_type="STANDARD NONELECTRIC"),
            "unknown": _site("unknown", campsite_type="MANAGEMENT"),
        }
        watch = _watch(watch_db, site_types=["hookups"])
        assert await _alerted(watch_db, watch, sites) == {"electric", "unknown"}

    @pytest.mark.asyncio
    async def test_misfits_stay_out_of_the_snapshot(self, watch_db: WatchDB):
        """A misfit opening up later must not alert either."""
        watch = _watch(watch_db, min_people=4)
        await _alerted(watch_db, watch, {"small": _site("small", max_people=2)})
        assert watch_db.get_latest_snapshot(watch.id).available_sites == {}

    @pytest.mark.asyncio
    async def test_wa_watch_uses_seeded_site_fit(self, watch_db: WatchDB, registry):
        park = "-2147483616"
        registry.bulk_upsert_wa_loops(
            park, [{"map_id": -1, "title": "Main", "description": FORT_EBEY_MAIN}],
        )
        registry.bulk_upsert_wa_sites(park, [
            {"resource_id": -27, "name": "27", "loop_map_id": -1, "max_capacity": 8,
             "allowed_equipment": FORT_EBEY_7},  # RV up to 30 ft
        ])
        gtc = AsyncMock(spec=GoingToCampClient)
        gtc.get_availability.return_value = make_campground_availability(park, {
            "-27": make_campsite_availability(
                campsite_id="-27", site="-27", campsite_type="STANDARD",
                dates_status={JUNE_1: "Available"},
            ),
        })
        too_long = watch_db.add_watch(Watch(
            facility_id=park, start_date="2027-06-01", end_date="2027-06-02",
            booking_system="wa_state", equipment="trailer", rig_length=35,
        ))
        result = await poll_watch(too_long, None, gtc, watch_db, registry)
        assert result.error is None
        assert result.changes == []

    @pytest.mark.asyncio
    async def test_template_watch_passes_filters_to_each_park(
        self, watch_db: WatchDB, registry,
    ):
        from tests.conftest import make_campground

        registry.upsert(make_campground(facility_id="232465", name="Camp", state="WA"))
        watch_db.add_watch(Watch(
            name="Pattern", start_date="2027-06-01", end_date="2027-06-02",
            watch_type="template", search_params='{"state": "WA"}', min_people=4,
        ))
        client = _client({"small": _site("small", max_people=2)})
        results = await poll_all(client, None, watch_db, registry, today=None)
        (result,) = results
        assert result.watch.min_people == 4
        assert result.changes == []


# ---------------------------------------------------------------------------
# API and CLI
# ---------------------------------------------------------------------------

WATCH_BODY = {"facility_id": "232465", "start_date": "2027-06-04", "end_date": "2027-06-05"}


class TestWatchApi:
    def test_create_with_filters_stores_and_returns_them(self, api_client):
        body = {**WATCH_BODY, "min_people": 4, "equipment": "trailer", "rig_length": 30,
                "site_types": ["hookups"]}
        data = api_client.post("/api/watches", json=body).json()
        assert (data["min_people"], data["equipment"], data["rig_length"], data["site_types"]) == (
            4, "trailer", 30, ["hookups"],
        )
        listed = api_client.get("/api/watches").json()
        assert listed[0]["equipment"] == "trailer"

    def test_create_without_filters_is_unfiltered(self, api_client):
        data = api_client.post("/api/watches", json=WATCH_BODY).json()
        assert (data["min_people"], data["equipment"], data["rig_length"], data["site_types"]) == (
            None, None, None, None,
        )

    def test_rig_length_only_kept_for_trailers(self, api_client):
        body = {**WATCH_BODY, "equipment": "tent", "rig_length": 30}
        assert api_client.post("/api/watches", json=body).json()["rig_length"] is None

    @pytest.mark.parametrize("bad", [
        {"equipment": "boat"},
        {"min_people": 0},
        {"min_people": 51},
        {"rig_length": 101, "equipment": "trailer"},
        {"site_types": ["yurt"]},
    ])
    def test_invalid_filters_are_rejected(self, api_client, bad):
        assert api_client.post("/api/watches", json={**WATCH_BODY, **bad}).status_code == 422


def test_cli_watch_add_stores_filters(tmp_path, monkeypatch, capsys):
    import argparse
    from unittest.mock import MagicMock

    from pnw_campsites import __main__ as cli

    registry = MagicMock()
    registry.booking_systems_for.return_value = []
    registry.get_by_facility_id.return_value = None
    monkeypatch.setattr(cli, "CampgroundRegistry", lambda: registry)
    db_path = tmp_path / "w.db"
    monkeypatch.setattr(cli, "WatchDB", lambda: WatchDB(db_path))

    import asyncio
    asyncio.run(cli.cmd_watch_add(argparse.Namespace(
        facility_id="232465", dates="2027-06-04:2027-06-05", nights=2, days=None,
        name=None, ntfy_topic=None, people=4, equipment="trailer", rig_length=30,
        site_types=["hookups"],
    )))

    with WatchDB(db_path) as db:
        (watch,) = db.list_watches()
    assert (watch.min_people, watch.equipment, watch.rig_length, watch.site_types) == (
        4, "trailer", 30, ["hookups"],
    )
    assert "Sites: 4 people · trailer 30 ft · hookups" in capsys.readouterr().out
