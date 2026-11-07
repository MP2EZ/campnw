"""Curated tag overrides applied by the registry at init.

Prod's registry.db lives on a Fly volume and is never re-seeded from the image,
so data fixes ship as an idempotent migration run every time the registry opens.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from pnw_campsites.enrichment.llm_tags import VALID_TAGS
from pnw_campsites.registry import tag_overrides
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.registry.tag_overrides import TAG_OVERRIDES, apply_tag_overrides

BLAKE = ("wa_state", "-2147483640")
SCHAFER = ("wa_state", "-2147483559")


def _seed(registry, key, tags, name="Test Park"):
    bs, fid = key
    return registry.upsert(
        Campground(
            facility_id=fid,
            name=name,
            booking_system=BookingSystem(bs),
            state="WA",
            tags=tags,
        )
    )


def _tags(registry, key) -> list[str]:
    bs, fid = key
    row = registry._conn.execute(
        "SELECT tags FROM campgrounds WHERE booking_system=? AND facility_id=?",
        (bs, fid),
    ).fetchone()
    return json.loads(row["tags"])


@pytest.fixture
def overrides(monkeypatch):
    """A tiny table so tests don't depend on the real curated data."""
    table = {
        ("recgov", "1"): {"add": ["boat-in"]},
        ("recgov", "2"): {"remove": ["beach"], "add": ["riverside"]},
        ("recgov", "3"): {"remove": ["beach"], "add": ["lakeside"]},
    }
    monkeypatch.setattr(tag_overrides, "TAG_OVERRIDES", table)
    return table


class TestApplyTagOverrides:
    def test_add_appends_without_touching_other_tags(self, registry, overrides):
        _seed(registry, ("recgov", "1"), ["fishing", "lakeside"])
        apply_tag_overrides(registry._conn)
        assert _tags(registry, ("recgov", "1")) == ["fishing", "lakeside", "boat-in"]

    def test_remove_and_add(self, registry, overrides):
        _seed(registry, ("recgov", "2"), ["beach", "fishing"])
        apply_tag_overrides(registry._conn)
        assert _tags(registry, ("recgov", "2")) == ["fishing", "riverside"]

    def test_add_is_not_duplicated_when_already_present(self, registry, overrides):
        _seed(registry, ("recgov", "2"), ["beach", "riverside"])
        apply_tag_overrides(registry._conn)
        assert _tags(registry, ("recgov", "2")) == ["riverside"]

    def test_idempotent(self, registry, overrides):
        _seed(registry, ("recgov", "1"), ["fishing"])
        _seed(registry, ("recgov", "2"), ["beach"])
        apply_tag_overrides(registry._conn)
        first = registry._conn.execute(
            "SELECT facility_id, tags, updated_at FROM campgrounds ORDER BY id"
        ).fetchall()
        apply_tag_overrides(registry._conn)
        apply_tag_overrides(registry._conn)
        second = registry._conn.execute(
            "SELECT facility_id, tags, updated_at FROM campgrounds ORDER BY id"
        ).fetchall()
        assert [tuple(r) for r in first] == [tuple(r) for r in second]

    def test_second_run_issues_no_writes(self, registry, overrides):
        _seed(registry, ("recgov", "1"), ["fishing"])
        apply_tag_overrides(registry._conn)
        before = registry._conn.total_changes
        apply_tag_overrides(registry._conn)
        assert registry._conn.total_changes == before

    def test_campgrounds_outside_table_untouched(self, registry, overrides):
        _seed(registry, ("recgov", "99"), ["beach", "lakeside"])
        apply_tag_overrides(registry._conn)
        assert _tags(registry, ("recgov", "99")) == ["beach", "lakeside"]

    def test_override_for_missing_campground_is_ignored(self, registry, overrides):
        apply_tag_overrides(registry._conn)  # nothing seeded; must not raise

    def test_same_facility_id_in_other_booking_system_untouched(
        self, registry, overrides
    ):
        _seed(registry, ("or_state", "1"), ["fishing"])
        apply_tag_overrides(registry._conn)
        assert _tags(registry, ("or_state", "1")) == ["fishing"]

    def test_does_not_bump_updated_at(self, registry, overrides):
        _seed(registry, ("recgov", "1"), [])
        before = registry._conn.execute(
            "SELECT updated_at FROM campgrounds"
        ).fetchone()[0]
        apply_tag_overrides(registry._conn)
        after = registry._conn.execute(
            "SELECT updated_at FROM campgrounds"
        ).fetchone()[0]
        assert before == after


class TestAppliedAtRegistryInit:
    def test_opening_registry_applies_overrides(self, tmp_path, overrides):
        path = tmp_path / "registry.db"
        with CampgroundRegistry(path) as reg:
            _seed(reg, ("recgov", "1"), ["fishing"])
        # A fresh open (what prod does on every boot) applies the migration.
        with CampgroundRegistry(path) as reg:
            assert _tags(reg, ("recgov", "1")) == ["fishing", "boat-in"]

    def test_tags_added_later_by_enrichment_survive_reopen(self, tmp_path, overrides):
        path = tmp_path / "registry.db"
        with CampgroundRegistry(path) as reg:
            cg = _seed(reg, ("recgov", "2"), ["beach"])
        with CampgroundRegistry(path) as reg:
            assert _tags(reg, ("recgov", "2")) == ["riverside"]
            # enrichment later adds unrelated tags
            reg.update_tags(cg.id, ["riverside", "fishing", "kid-friendly"])
        with CampgroundRegistry(path) as reg:
            assert _tags(reg, ("recgov", "2")) == [
                "riverside", "fishing", "kid-friendly",
            ]

    def test_reviewed_override_wins_if_enrichment_readds_removed_tag(
        self, tmp_path, overrides
    ):
        path = tmp_path / "registry.db"
        with CampgroundRegistry(path) as reg:
            cg = _seed(reg, ("recgov", "3"), ["beach"])
            reg.update_tags(cg.id, ["beach", "lakeside", "swimming"])
        with CampgroundRegistry(path) as reg:
            assert _tags(reg, ("recgov", "3")) == ["lakeside", "swimming"]

    def test_legacy_db_without_tags_json_is_not_a_crash(self, tmp_path, overrides):
        """A row whose tags column is NULL/empty is treated as no tags."""
        path = tmp_path / "registry.db"
        with CampgroundRegistry(path) as reg:
            _seed(reg, ("recgov", "1"), [])
            reg._conn.execute("UPDATE campgrounds SET tags=NULL")
            reg._conn.commit()
        with CampgroundRegistry(path) as reg:
            assert _tags(reg, ("recgov", "1")) == ["boat-in"]


class TestCuratedTable:
    def test_tags_are_in_the_vocabulary(self):
        for key, change in TAG_OVERRIDES.items():
            for tag in change.get("add", []) + change.get("remove", []):
                assert tag in VALID_TAGS, f"{key}: unknown tag {tag!r}"

    def test_add_and_remove_never_overlap(self):
        for key, change in TAG_OVERRIDES.items():
            assert not set(change.get("add", [])) & set(change.get("remove", [])), key

    def test_keys_use_real_booking_systems(self):
        for bs, fid in TAG_OVERRIDES:
            BookingSystem(bs)
            assert fid.strip() == fid and fid

    def test_blake_island_is_boat_in(self):
        assert "boat-in" in TAG_OVERRIDES[BLAKE]["add"]

    def test_river_parks_lose_beach(self):
        assert "beach" in TAG_OVERRIDES[SCHAFER]["remove"]

    def test_saltwater_parks_keep_beach(self):
        # Blake is a saltwater marine park: boat-in is added, beach is kept.
        assert "beach" not in TAG_OVERRIDES[BLAKE].get("remove", [])


def test_sqlite_row_factory_not_required(tmp_path, overrides):
    """apply_tag_overrides works on a plain connection (no Row factory)."""
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute(
        "CREATE TABLE campgrounds (id INTEGER PRIMARY KEY, facility_id TEXT,"
        " booking_system TEXT, tags TEXT)"
    )
    conn.execute(
        "INSERT INTO campgrounds (facility_id, booking_system, tags)"
        " VALUES ('1', 'recgov', '[]')"
    )
    conn.commit()
    apply_tag_overrides(conn)
    assert json.loads(conn.execute("SELECT tags FROM campgrounds").fetchone()[0]) == [
        "boat-in"
    ]
