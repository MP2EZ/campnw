"""WA site/loop metadata shipped as a JSON fixture and imported at registry open.

GoingToCamp blocks Fly's egress IPs, so prod can't run the metadata seeder. The
seeder exports to a fixture in the repo; every registry open imports it once
per fixture change.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pnw_campsites.registry import wa_site_fixture
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.registry.wa_site_fixture import (
    FIXTURE_PATH,
    apply_wa_site_fixture,
    export_wa_site_fixture,
)

PARK = "-2147483598"  # Lake Easton
OTHER_PARK = "-2147483601"  # Kanaskat-Palmer
EQUIP = [
    {"equipmentCategoryId": -32768, "subEquipmentCategoryId": -32768},
    {"equipmentCategoryId": -32767, "subEquipmentCategoryId": -32760},
]


def _add_park(registry: CampgroundRegistry, facility_id: str = PARK) -> None:
    registry.upsert(Campground(
        facility_id=facility_id, name=f"Park {facility_id}",
        booking_system=BookingSystem.WA_STATE, state="WA",
    ))


def _seed_rows(registry: CampgroundRegistry) -> None:
    registry.bulk_upsert_wa_loops(PARK, [
        {"map_id": 20, "title": "Loop B", "description": "Sites 40-60, 30A power"},
        {"map_id": 10, "title": "Loop A", "description": ""},
    ])
    registry.bulk_upsert_wa_sites(PARK, [
        {"resource_id": 2, "name": "41", "loop_map_id": 20, "max_capacity": 6,
         "min_capacity": 1, "allowed_equipment": EQUIP},
        {"resource_id": 1, "name": "1", "loop_map_id": 10, "max_capacity": None,
         "min_capacity": None, "allowed_equipment": []},
    ])


@pytest.fixture
def exported(registry, tmp_path) -> Path:
    """A fixture file exported from a registry holding one park's rows."""
    _seed_rows(registry)
    path = tmp_path / "wa_state_sites.json"
    export_wa_site_fixture(registry._conn, path)
    return path


@pytest.fixture
def fresh(tmp_path) -> CampgroundRegistry:
    """A registry with the WA park but no site rows: prod before the import."""
    reg = CampgroundRegistry(tmp_path / "fresh.db")
    _add_park(reg)
    yield reg
    reg.close()


def _site_names(registry: CampgroundRegistry) -> dict[int, str]:
    return {
        r["resource_id"]: r["name"]
        for r in registry._conn.execute("SELECT resource_id, name FROM wa_state_sites")
    }


class TestExport:
    def test_one_row_per_line_sorted_by_park_then_id(self, exported):
        lines = exported.read_text().splitlines()
        loop_lines = [ln for ln in lines if '"map_id"' in ln]
        site_lines = [ln for ln in lines if '"resource_id"' in ln]
        assert [json.loads(ln.rstrip(","))["map_id"] for ln in loop_lines] == [10, 20]
        assert [json.loads(ln.rstrip(","))["resource_id"] for ln in site_lines] == [1, 2]

    def test_equipment_stored_as_pairs_without_timestamps(self, exported):
        data = json.loads(exported.read_text())
        site = next(s for s in data["sites"] if s["resource_id"] == 2)
        assert site["allowed_equipment"] == [[-32768, -32768], [-32767, -32760]]
        assert "updated_at" not in site
        assert "updated_at" not in data["loops"][0]

    def test_reexport_after_import_is_byte_identical(self, exported, fresh, tmp_path):
        apply_wa_site_fixture(fresh._conn, exported)
        again = tmp_path / "again.json"
        export_wa_site_fixture(fresh._conn, again)
        assert again.read_bytes() == exported.read_bytes()


class TestApply:
    def test_imports_sites_and_loops_into_the_site_index(self, exported, fresh):
        assert apply_wa_site_fixture(fresh._conn, exported) == 2
        index = fresh.get_wa_site_index(PARK)
        assert index[2].name == "41"
        assert index[2].loop_title == "Loop B"
        assert index[2].loop_description == "Sites 40-60, 30A power"
        assert index[2].max_capacity == 6
        assert index[2].allowed_equipment == EQUIP
        assert index[1].max_capacity is None

    def test_second_apply_of_same_fixture_is_a_noop(self, exported, fresh):
        apply_wa_site_fixture(fresh._conn, exported)
        fresh._conn.execute("UPDATE wa_state_sites SET name='edited' WHERE resource_id=1")
        fresh._conn.commit()
        assert apply_wa_site_fixture(fresh._conn, exported) == 0
        assert _site_names(fresh)[1] == "edited"

    def test_changed_fixture_upserts_by_resource_id(self, exported, fresh):
        apply_wa_site_fixture(fresh._conn, exported)
        data = json.loads(exported.read_text())
        data["sites"][0]["name"] = "1A"
        exported.write_text(json.dumps(data))
        assert apply_wa_site_fixture(fresh._conn, exported) == 2
        assert _site_names(fresh) == {1: "1A", 2: "41"}

    def test_never_deletes_rows_the_fixture_lacks(self, exported, fresh):
        _add_park(fresh, OTHER_PARK)
        fresh.bulk_upsert_wa_sites(OTHER_PARK, [
            {"resource_id": 99, "name": "X1", "loop_map_id": 99},
        ])
        fresh.bulk_upsert_wa_loops(OTHER_PARK, [{"map_id": 99, "title": "Loop X"}])
        apply_wa_site_fixture(fresh._conn, exported)
        assert _site_names(fresh)[99] == "X1"
        assert fresh.get_wa_site_index(OTHER_PARK)[99].loop_title == "Loop X"

    def test_waits_for_wa_parks_before_recording_the_import(self, exported, tmp_path):
        reg = CampgroundRegistry(tmp_path / "empty.db")
        try:
            assert apply_wa_site_fixture(reg._conn, exported) == 0
            _add_park(reg)
            assert apply_wa_site_fixture(reg._conn, exported) == 2
        finally:
            reg.close()

    def test_missing_fixture_is_a_noop(self, fresh, tmp_path):
        assert apply_wa_site_fixture(fresh._conn, tmp_path / "nope.json") == 0


def test_registry_open_imports_the_fixture(exported, tmp_path, monkeypatch):
    """Prod's volume registry predates the fixture: the next boot imports it."""
    monkeypatch.setattr(wa_site_fixture, "FIXTURE_PATH", exported)
    path = tmp_path / "old.db"
    with CampgroundRegistry(path) as reg:
        _add_park(reg)
    with CampgroundRegistry(path) as reg:
        assert set(reg.get_wa_site_index(PARK)) == {1, 2}


def test_shipped_fixture_covers_every_wa_park_in_the_seed_registry():
    seed = Path(__file__).resolve().parents[1] / "data" / "registry.db"
    conn = sqlite3.connect(f"file:{seed}?mode=ro", uri=True)
    try:
        parks = {
            r[0] for r in conn.execute(
                "SELECT facility_id FROM campgrounds WHERE booking_system='wa_state'"
            )
        }
    finally:
        conn.close()
    data = json.loads(FIXTURE_PATH.read_text())
    assert parks
    assert parks <= {s["park_facility_id"] for s in data["sites"]}
