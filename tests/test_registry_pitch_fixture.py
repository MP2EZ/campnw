"""LLM pitch copy shipped as a JSON fixture and imported at registry open.

Prod's registry.db lives on a Fly volume that is never re-seeded from the image,
so regenerated pitches ship as a fixture. Every registry open imports it once
per fixture change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pnw_campsites.registry import pitch_fixture
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.registry.pitch_fixture import (
    FIXTURE_PATH,
    apply_pitch_fixture,
    export_pitch_fixture,
)


def _add(
    registry: CampgroundRegistry,
    facility_id: str,
    system: BookingSystem = BookingSystem.RECGOV,
    pitch: str = "",
) -> None:
    registry.upsert(Campground(
        facility_id=facility_id, name=f"Camp {facility_id}",
        booking_system=system, state="WA",
    ))
    if pitch:
        cg = registry.get_by_facility_id(facility_id, system)
        registry.update_description(cg.id, pitch, f"{pitch} Longer.", "tent campers")


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"pitches": rows}))
    return path


def _row(facility_id: str, pitch: str, system: str = "recgov") -> dict:
    return {
        "booking_system": system, "facility_id": facility_id,
        "elevator_pitch": pitch, "description_rewrite": f"{pitch} Longer.",
        "best_for": "anglers",
    }


def _pitch(registry: CampgroundRegistry, facility_id: str,
           system: BookingSystem = BookingSystem.RECGOV) -> str:
    return registry.get_by_facility_id(facility_id, system).elevator_pitch


class TestApply:
    def test_overwrites_existing_copy(self, registry, tmp_path):
        _add(registry, "100", pitch="Peaceful haven for solitude seekers.")
        path = _write(tmp_path / "p.json", [_row("100", "Lakeside camp with 40 sites.")])

        assert apply_pitch_fixture(registry._conn, path) == 1

        cg = registry.get_by_facility_id("100", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Lakeside camp with 40 sites."
        assert cg.description_rewrite == "Lakeside camp with 40 sites. Longer."
        assert cg.best_for == "anglers"

    def test_keys_on_booking_system_and_facility_id(self, registry, tmp_path):
        _add(registry, "7", BookingSystem.RECGOV, pitch="Old recgov.")
        _add(registry, "7", BookingSystem.WA_STATE, pitch="Old wa.")
        path = _write(tmp_path / "p.json", [_row("7", "New wa.", system="wa_state")])

        apply_pitch_fixture(registry._conn, path)

        assert _pitch(registry, "7", BookingSystem.RECGOV) == "Old recgov."
        assert _pitch(registry, "7", BookingSystem.WA_STATE) == "New wa."

    def test_rows_missing_from_registry_are_ignored(self, registry, tmp_path):
        _add(registry, "100", pitch="Old.")
        path = _write(tmp_path / "p.json", [_row("999", "Nowhere.")])

        assert apply_pitch_fixture(registry._conn, path) == 0
        assert _pitch(registry, "100") == "Old."

    def test_unchanged_fixture_is_not_reimported(self, registry, tmp_path):
        _add(registry, "100")
        path = _write(tmp_path / "p.json", [_row("100", "Fixture copy.")])
        apply_pitch_fixture(registry._conn, path)
        # A local regen after the import must survive the next open.
        cg = registry.get_by_facility_id("100", BookingSystem.RECGOV)
        registry.update_description(cg.id, "Local edit.", "", "")

        assert apply_pitch_fixture(registry._conn, path) == 0
        assert _pitch(registry, "100") == "Local edit."

    def test_changed_fixture_is_reimported(self, registry, tmp_path):
        _add(registry, "100")
        path = _write(tmp_path / "p.json", [_row("100", "First.")])
        apply_pitch_fixture(registry._conn, path)
        _write(path, [_row("100", "Second.")])

        assert apply_pitch_fixture(registry._conn, path) == 1
        assert _pitch(registry, "100") == "Second."

    def test_empty_registry_defers_import(self, registry, tmp_path):
        path = _write(tmp_path / "p.json", [_row("100", "Fixture copy.")])
        assert apply_pitch_fixture(registry._conn, path) == 0
        # Not recorded: once campgrounds are seeded, the next open imports.
        _add(registry, "100")
        assert apply_pitch_fixture(registry._conn, path) == 1
        assert _pitch(registry, "100") == "Fixture copy."

    def test_missing_file_is_a_noop(self, registry, tmp_path):
        _add(registry, "100", pitch="Old.")
        assert apply_pitch_fixture(registry._conn, tmp_path / "absent.json") == 0
        assert _pitch(registry, "100") == "Old."

    def test_runs_on_registry_open(self, tmp_path, monkeypatch):
        db = tmp_path / "registry.db"
        with CampgroundRegistry(db) as reg:
            _add(reg, "100", pitch="Old.")
        path = _write(tmp_path / "p.json", [_row("100", "Imported at open.")])
        monkeypatch.setattr(pitch_fixture, "FIXTURE_PATH", path)

        with CampgroundRegistry(db) as reg:
            assert _pitch(reg, "100") == "Imported at open."


class TestExport:
    def test_round_trip(self, registry, tmp_path):
        _add(registry, "200", pitch="Riverside camp with 12 sites.")
        _add(registry, "-5", BookingSystem.WA_STATE, pitch="Saltwater park with 80 sites.")
        _add(registry, "300")  # no pitch: left out
        path = tmp_path / "p.json"

        assert export_pitch_fixture(registry._conn, path) == 2

        other = CampgroundRegistry(tmp_path / "other.db")
        _add(other, "200")
        _add(other, "-5", BookingSystem.WA_STATE)
        assert apply_pitch_fixture(other._conn, path) == 2
        assert _pitch(other, "200") == "Riverside camp with 12 sites."
        assert _pitch(other, "-5", BookingSystem.WA_STATE) == "Saltwater park with 80 sites."
        other.close()

    def test_one_row_per_line_sorted(self, registry, tmp_path):
        _add(registry, "b", pitch="B.")
        _add(registry, "a", pitch="A.")
        path = tmp_path / "p.json"
        export_pitch_fixture(registry._conn, path)

        lines = path.read_text().splitlines()
        assert lines[0] == '{"pitches": ['
        assert '"facility_id": "a"' in lines[1]
        assert '"facility_id": "b"' in lines[2]
        assert json.loads(path.read_text())["pitches"][0]["elevator_pitch"] == "A."


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="no pitch fixture checked in")
def test_checked_in_fixture_is_valid():
    rows = json.loads(FIXTURE_PATH.read_text())["pitches"]
    keys = {(r["booking_system"], r["facility_id"]) for r in rows}
    assert len(keys) == len(rows)
    for r in rows:
        assert r["elevator_pitch"], r
        assert len(r["elevator_pitch"]) <= 120, r
