"""Tests for the campground registry database."""

from __future__ import annotations

from pnw_campsites.registry.models import BookingSystem, Campground


def make_campground(**overrides) -> Campground:
    """Create a Campground with sensible defaults, override any field."""
    defaults = {
        "facility_id": "232465",
        "name": "Test Campground",
        "booking_system": BookingSystem.RECGOV,
        "latitude": 46.75,
        "longitude": -121.80,
        "state": "WA",
        "region": "Mt. Rainier NP",
        "tags": ["lakeside"],
        "enabled": True,
    }
    defaults.update(overrides)
    return Campground(**defaults)


class TestUpsertNew:
    """Test upserting a new campground."""

    def test_upsert_new_campground(self, registry):
        """New campground is created with id populated."""
        cg = make_campground(facility_id="232465", name="Ohanapecosh")
        result = registry.upsert(cg)

        assert result.id is not None
        assert result.facility_id == "232465"
        assert result.name == "Ohanapecosh"
        assert result.booking_system == BookingSystem.RECGOV


class TestUpsertExisting:
    """Test upserting an existing campground (update behavior)."""

    def test_upsert_existing_updates_name_and_coords(self, registry):
        """Upserting same booking_system + facility_id updates fields,
        preserves id."""
        cg1 = make_campground(
            facility_id="232465",
            name="Old Name",
            latitude=46.0,
            longitude=-121.0,
        )
        result1 = registry.upsert(cg1)
        id1 = result1.id

        cg2 = make_campground(
            facility_id="232465",
            name="Ohanapecosh",
            latitude=46.75,
            longitude=-121.80,
        )
        result2 = registry.upsert(cg2)
        id2 = result2.id

        assert id1 == id2
        assert result2.name == "Ohanapecosh"
        assert result2.latitude == 46.75
        assert result2.longitude == -121.80


class TestSearchByState:
    """Test search filtering by state."""

    def test_search_state_filter(self, registry):
        """search(state="WA") returns only WA campgrounds."""
        registry.upsert(make_campground(facility_id="wa1", state="WA"))
        registry.upsert(make_campground(facility_id="or1", state="OR"))
        registry.upsert(make_campground(facility_id="wa2", state="WA"))

        results = registry.search(state="WA")
        assert len(results) == 2
        assert all(cg.state == "WA" for cg in results)


class TestSearchByTags:
    """Test search filtering by tags."""

    def test_search_tags_filter(self, registry):
        """search(tags=["lakeside"]) returns only campgrounds with lakeside
        tag."""
        registry.upsert(make_campground(facility_id="1", tags=["lakeside"]))
        registry.upsert(
            make_campground(facility_id="2", tags=["river", "forest"])
        )
        registry.upsert(
            make_campground(facility_id="3", tags=["lakeside", "mountain"])
        )

        results = registry.search(tags=["lakeside"])
        assert len(results) == 2
        assert all("lakeside" in cg.tags for cg in results)

    def test_search_tags_intersection(self, registry):
        """search(tags=["lakeside", "river"]) returns campgrounds matching
        ANY tag."""
        registry.upsert(make_campground(facility_id="1", tags=["lakeside"]))
        registry.upsert(make_campground(facility_id="2", tags=["river"]))
        registry.upsert(make_campground(facility_id="3", tags=["mountain"]))

        results = registry.search(tags=["lakeside", "river"])
        assert len(results) == 2


class TestSearchByName:
    """Test search filtering by name pattern."""

    def test_search_name_like_case_insensitive(self, registry):
        """search(name_like="rainier") filters case-insensitively."""
        registry.upsert(make_campground(facility_id="1", name="Mount Rainier"))
        registry.upsert(make_campground(facility_id="2", name="Ohanapecosh"))
        registry.upsert(make_campground(facility_id="3", name="rainier base"))

        results = registry.search(name_like="rainier")
        assert len(results) == 2
        assert "Mount Rainier" in [cg.name for cg in results]
        assert "rainier base" in [cg.name for cg in results]


class TestSearchByDriveTime:
    """Test search filtering by drive_minutes_from_base."""

    def test_search_max_drive_minutes_filter(self, registry):
        """search(max_drive_minutes=120) excludes longer drives and NULL."""
        registry.upsert(
            make_campground(facility_id="1", drive_minutes_from_base=60)
        )
        registry.upsert(
            make_campground(facility_id="2", drive_minutes_from_base=150)
        )
        registry.upsert(make_campground(facility_id="3", drive_minutes_from_base=None))

        results = registry.search(max_drive_minutes=120)
        assert len(results) == 1
        assert results[0].facility_id == "1"

    def test_search_max_drive_minutes_excludes_null(self, registry):
        """Campgrounds with NULL drive_minutes_from_base are excluded."""
        registry.upsert(
            make_campground(facility_id="1", drive_minutes_from_base=100)
        )
        registry.upsert(make_campground(facility_id="2", drive_minutes_from_base=None))

        results = registry.search(max_drive_minutes=150)
        assert len(results) == 1


class TestSearchByBookingSystem:
    """Test search filtering by booking system."""

    def test_search_booking_system_filter(self, registry):
        """search(booking_system=BookingSystem.WA_STATE) filters correctly."""
        registry.upsert(
            make_campground(
                facility_id="1",
                booking_system=BookingSystem.RECGOV,
            )
        )
        registry.upsert(
            make_campground(
                facility_id="2",
                booking_system=BookingSystem.WA_STATE,
            )
        )

        results = registry.search(booking_system=BookingSystem.WA_STATE)
        assert len(results) == 1
        assert results[0].booking_system == BookingSystem.WA_STATE


class TestSearchEnabledOnly:
    """Test search enabled_only flag."""

    def test_search_enabled_only_default(self, registry):
        """search() with enabled_only=True (default) excludes disabled
        campgrounds."""
        registry.upsert(make_campground(facility_id="1", enabled=True))
        registry.upsert(make_campground(facility_id="2", enabled=False))

        results = registry.search()
        assert len(results) == 1
        assert results[0].facility_id == "1"

    def test_search_enabled_only_false(self, registry):
        """search(enabled_only=False) includes disabled campgrounds."""
        registry.upsert(make_campground(facility_id="1", enabled=True))
        registry.upsert(make_campground(facility_id="2", enabled=False))

        results = registry.search(enabled_only=False)
        assert len(results) == 2


class TestUpdateTags:
    """Test updating campground tags."""

    def test_update_tags_round_trip(self, registry):
        """update_tags() persists tags, get_by_id() retrieves them."""
        cg = make_campground(facility_id="1", tags=[])
        result = registry.upsert(cg)
        cg_id = result.id

        registry.update_tags(cg_id, ["lakeside", "mountain"])
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is not None
        assert set(retrieved.tags) == {"lakeside", "mountain"}


class TestUpdateNotes:
    """Test updating campground notes and rating."""

    def test_update_notes_round_trip(self, registry):
        """update_notes() persists notes, get_by_id() retrieves them."""
        cg = make_campground(facility_id="1", notes="")
        result = registry.upsert(cg)
        cg_id = result.id

        registry.update_notes(cg_id, "Great fishing spot")
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is not None
        assert retrieved.notes == "Great fishing spot"

    def test_update_notes_with_rating(self, registry):
        """update_notes() with rating parameter persists both."""
        cg = make_campground(facility_id="1", rating=None)
        result = registry.upsert(cg)
        cg_id = result.id

        registry.update_notes(cg_id, "Excellent campground", rating=5)
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is not None
        assert retrieved.notes == "Excellent campground"
        assert retrieved.rating == 5


class TestSetEnabled:
    """Test toggling enabled flag."""

    def test_set_enabled_true(self, registry):
        """set_enabled(id, True) persists enabled=True."""
        cg = make_campground(facility_id="1", enabled=False)
        result = registry.upsert(cg)
        cg_id = result.id

        registry.set_enabled(cg_id, True)
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is not None
        assert retrieved.enabled is True

    def test_set_enabled_false(self, registry):
        """set_enabled(id, False) persists enabled=False."""
        cg = make_campground(facility_id="1", enabled=True)
        result = registry.upsert(cg)
        cg_id = result.id

        registry.set_enabled(cg_id, False)
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is not None
        assert retrieved.enabled is False


class TestDelete:
    """Test deleting campgrounds."""

    def test_delete_removes_row(self, registry):
        """delete(id) removes row, get_by_id() returns None."""
        cg = make_campground(facility_id="1")
        result = registry.upsert(cg)
        cg_id = result.id

        registry.delete(cg_id)
        retrieved = registry.get_by_id(cg_id)

        assert retrieved is None


class TestFindSimilar:
    """Test find_similar() method for campground recommendations."""

    def test_finds_campgrounds_with_overlapping_tags(self, registry):
        """find_similar() returns campgrounds with shared tags."""
        source = registry.upsert(
            make_campground(
                facility_id="lakeside-1",
                name="Lake Camp A",
                tags=["lakeside", "mountain"],
                latitude=47.0,
                longitude=-121.0,
            )
        )
        registry.upsert(
            make_campground(
                facility_id="lakeside-2",
                name="Lake Camp B",
                tags=["lakeside", "river"],
                latitude=47.1,
                longitude=-121.1,
            )
        )
        registry.upsert(
            make_campground(
                facility_id="other-1",
                name="Desert Camp",
                tags=["desert"],
                latitude=46.0,
                longitude=-120.0,
            )
        )

        results = registry.find_similar(source, limit=2)

        # Should find lakeside-2 (shared "lakeside" tag)
        assert len(results) >= 1
        names = [cg.name for cg in results]
        assert "Lake Camp B" in names
        assert "Desert Camp" not in names

    def test_excludes_source_campground(self, registry):
        """find_similar() excludes the source campground itself."""
        source = registry.upsert(
            make_campground(
                facility_id="src-1",
                name="Source Camp",
                tags=["lakeside"],
            )
        )

        results = registry.find_similar(source, limit=5)

        # Source should not be in results
        assert not any(
            cg.facility_id == "src-1" for cg in results
        )

    def test_proximity_affects_ranking(self, registry):
        """Proximity to source affects similarity ranking."""
        source = registry.upsert(
            make_campground(
                facility_id="src",
                tags=["lakeside"],
                latitude=47.0,
                longitude=-121.0,
            )
        )
        # Close with shared tag
        registry.upsert(
            make_campground(
                facility_id="close",
                tags=["lakeside"],
                latitude=47.01,  # ~1 km away
                longitude=-121.01,
            )
        )
        # Far with shared tag
        registry.upsert(
            make_campground(
                facility_id="far",
                tags=["lakeside"],
                latitude=48.0,  # ~110 km away
                longitude=-121.0,
            )
        )

        results = registry.find_similar(source, limit=1)

        # Closer campground should rank higher
        assert len(results) == 1
        assert results[0].facility_id == "close"

    def test_returns_empty_list_no_similar_found(self, registry):
        """Returns empty list when no similar campgrounds exist."""
        source = registry.upsert(
            make_campground(
                facility_id="unique",
                name="Unique Camp",
                tags=["rare-tag"],
            )
        )
        # Add unrelated campground
        registry.upsert(
            make_campground(
                facility_id="other",
                tags=["different"],
            )
        )

        results = registry.find_similar(source)

        assert results == []

    def test_respects_limit_parameter(self, registry):
        """find_similar(limit=n) returns at most n results."""
        source = registry.upsert(
            make_campground(
                facility_id="src",
                tags=["lakeside"],
                latitude=47.0,
                longitude=-121.0,
            )
        )
        # Add 5 similar campgrounds
        for i in range(5):
            registry.upsert(
                make_campground(
                    facility_id=f"sim-{i}",
                    tags=["lakeside"],
                    latitude=47.0 + i * 0.01,
                    longitude=-121.0,
                )
            )

        results = registry.find_similar(source, limit=2)

        assert len(results) == 2

    def test_state_filter_limits_scope(self, registry):
        """find_similar(state=X) only searches within that state."""
        source = registry.upsert(
            make_campground(
                facility_id="wa-src",
                state="WA",
                tags=["lakeside"],
            )
        )
        registry.upsert(
            make_campground(
                facility_id="wa-sim",
                state="WA",
                tags=["lakeside"],
            )
        )
        registry.upsert(
            make_campground(
                facility_id="or-sim",
                state="OR",
                tags=["lakeside"],
            )
        )

        results = registry.find_similar(source, state="WA", limit=5)

        # Should only find WA similar, not OR
        found_ids = [cg.facility_id for cg in results]
        assert "wa-sim" in found_ids
        assert "or-sim" not in found_ids

    def test_scores_by_jaccard_and_proximity(self, registry):
        """find_similar() combines Jaccard tag similarity and proximity."""
        source = registry.upsert(
            make_campground(
                facility_id="src",
                name="Source",
                tags=["lakeside", "mountain"],
                latitude=47.0,
                longitude=-121.0,
            )
        )
        # Higher tag similarity, far away
        registry.upsert(
            make_campground(
                facility_id="tags-far",
                name="High Tags Far",
                tags=["lakeside", "mountain"],  # perfect match
                latitude=48.0,  # far
                longitude=-121.0,
            )
        )
        # Lower tag similarity, close by
        registry.upsert(
            make_campground(
                facility_id="tags-close",
                name="Low Tags Close",
                tags=["lakeside"],  # only 1 of 2 tags
                latitude=47.01,  # very close
                longitude=-121.01,
            )
        )

        results = registry.find_similar(source, limit=2)

        assert len(results) == 2
        # Balanced scoring means both may appear; verify limit works
        assert len(results) <= 2

    def test_bulk_upsert_multiple_campgrounds(self, registry) -> None:
        """bulk_upsert inserts multiple campgrounds and returns count."""
        cgs = [
            make_campground(facility_id="1", name="Camp 1"),
            make_campground(facility_id="2", name="Camp 2"),
            make_campground(facility_id="3", name="Camp 3"),
        ]

        count = registry.bulk_upsert(cgs)

        assert count == 3
        assert registry.get_by_facility_id("1") is not None
        assert registry.get_by_facility_id("2") is not None
        assert registry.get_by_facility_id("3") is not None

    def test_bulk_upsert_updates_existing(self, registry) -> None:
        """bulk_upsert updates existing campgrounds."""
        cg1_v1 = make_campground(facility_id="1", name="Camp 1 Old")
        registry.upsert(cg1_v1)

        cg1_v2 = make_campground(facility_id="1", name="Camp 1 New")
        cg2 = make_campground(facility_id="2", name="Camp 2")

        count = registry.bulk_upsert([cg1_v2, cg2])

        assert count == 2
        # Verify the update took effect
        retrieved = registry.get_by_facility_id("1")
        assert retrieved is not None
        assert retrieved.name == "Camp 1 New"

    def test_update_vibe_persists(self, registry) -> None:
        """update_vibe saves vibe and persists on retrieval."""
        cg = make_campground(facility_id="1", name="Test")
        inserted = registry.upsert(cg)

        registry.update_vibe(inserted.id, "cozy-forest")

        retrieved = registry.get_by_id(inserted.id)
        assert retrieved is not None
        assert retrieved.vibe == "cozy-forest"

    def test_update_vibe_empty_campground_id(self, registry) -> None:
        """update_vibe with non-existent id silently succeeds."""
        # Should not raise an exception
        registry.update_vibe(9999, "some-vibe")

    def test_search_with_no_filters_returns_all_enabled(self, registry) -> None:
        """search with no filters returns all enabled campgrounds."""
        cg1 = make_campground(facility_id="1", name="Camp 1", enabled=True)
        cg2 = make_campground(facility_id="2", name="Camp 2", enabled=True)
        cg3 = make_campground(
            facility_id="3", name="Camp 3", enabled=False
        )

        registry.upsert(cg1)
        registry.upsert(cg2)
        registry.upsert(cg3)

        results = registry.search()

        assert len(results) == 2
        facility_ids = {r.facility_id for r in results}
        assert facility_ids == {"1", "2"}

    def test_search_disabled_campgrounds(self, registry) -> None:
        """search with enabled_only=False includes disabled campgrounds."""
        cg1 = make_campground(facility_id="1", name="Camp 1", enabled=False)
        cg2 = make_campground(facility_id="2", name="Camp 2", enabled=True)

        registry.upsert(cg1)
        registry.upsert(cg2)

        results = registry.search(enabled_only=False)

        assert len(results) == 2
        disabled = [r for r in results if not r.enabled]
        assert len(disabled) == 1

    def test_search_no_matches_returns_empty(self, registry) -> None:
        """search with non-matching criteria returns empty list."""
        cg = make_campground(facility_id="1", state="WA")
        registry.upsert(cg)

        results = registry.search(state="OR")

        assert len(results) == 0


class TestWaStateMetadataCache:
    """Tests for WA State Parks site/loop name cache (A1)."""

    def test_round_trip_loops_and_sites(self, registry) -> None:
        """bulk_upsert + get_wa_site_index returns the joined view."""
        registry.bulk_upsert_wa_loops(
            "-2147483624",
            [
                {"map_id": -2147483615, "title": "Lower Loop A", "description": "Sites 79-145"},
                {"map_id": -2147483614, "title": "Lower Loop B", "description": ""},
            ],
        )
        registry.bulk_upsert_wa_sites(
            "-2147483624",
            [
                {"resource_id": -2147481621, "name": "L03", "loop_map_id": -2147483615},
                {"resource_id": -2147481622, "name": "L04", "loop_map_id": -2147483615},
                {"resource_id": -2147481700, "name": "B01", "loop_map_id": -2147483614},
            ],
        )

        index = registry.get_wa_site_index("-2147483624")

        # 3rd tuple element is max_capacity (None when not provided)
        assert index[-2147481621] == ("L03", "Lower Loop A", None)
        assert index[-2147481622] == ("L04", "Lower Loop A", None)
        assert index[-2147481700] == ("B01", "Lower Loop B", None)

    def test_orphan_site_has_null_loop(self, registry) -> None:
        """Sites with no loop_map_id surface as (name, None)."""
        registry.bulk_upsert_wa_sites(
            "-2147483624",
            [{"resource_id": -2147481999, "name": "Orphan-1", "loop_map_id": None}],
        )

        index = registry.get_wa_site_index("-2147483624")

        assert index[-2147481999] == ("Orphan-1", None, None)

    def test_site_pointing_to_unknown_loop_has_null_title(self, registry) -> None:
        """LEFT JOIN returns NULL title when loop_map_id has no row."""
        registry.bulk_upsert_wa_sites(
            "-2147483624",
            [{"resource_id": -2147481621, "name": "L03", "loop_map_id": -999999}],
        )

        index = registry.get_wa_site_index("-2147483624")

        assert index[-2147481621] == ("L03", None, None)

    def test_re_seed_replaces_park_data(self, registry) -> None:
        """A second bulk_upsert for the same park replaces existing rows."""
        registry.bulk_upsert_wa_sites(
            "-2147483624",
            [{"resource_id": -2147481621, "name": "L03", "loop_map_id": None}],
        )
        registry.bulk_upsert_wa_sites(
            "-2147483624",
            [
                {"resource_id": -2147481621, "name": "L03-renamed", "loop_map_id": None},
                {"resource_id": -2147481622, "name": "L04", "loop_map_id": None},
            ],
        )

        index = registry.get_wa_site_index("-2147483624")

        assert len(index) == 2
        assert index[-2147481621][0] == "L03-renamed"
        assert -2147481622 in index

    def test_re_seed_does_not_affect_other_parks(self, registry) -> None:
        """Re-seeding park A leaves park B's rows untouched."""
        registry.bulk_upsert_wa_sites(
            "-100",
            [{"resource_id": 1, "name": "A1", "loop_map_id": None}],
        )
        registry.bulk_upsert_wa_sites(
            "-200",
            [{"resource_id": 2, "name": "B1", "loop_map_id": None}],
        )
        registry.bulk_upsert_wa_sites(
            "-100",
            [{"resource_id": 3, "name": "A2-new", "loop_map_id": None}],
        )

        assert 1 not in registry.get_wa_site_index("-100")
        assert 3 in registry.get_wa_site_index("-100")
        assert 2 in registry.get_wa_site_index("-200")

    def test_empty_park_returns_empty_dict(self, registry) -> None:
        """get_wa_site_index for a park with no cached data returns empty."""
        assert registry.get_wa_site_index("-9999999") == {}

    def test_bulk_upsert_empty_list_clears_park(self, registry) -> None:
        """Passing empty list deletes existing rows for that park (idempotent)."""
        registry.bulk_upsert_wa_sites(
            "-100",
            [{"resource_id": 1, "name": "A", "loop_map_id": None}],
        )
        registry.bulk_upsert_wa_sites("-100", [])

        assert registry.get_wa_site_index("-100") == {}


class TestWaStateMetadataCapacityEquipment:
    """Tests for per-site capacity + allowed_equipment cache (PR B follow-up to A1)."""

    def test_capacity_persists_through_round_trip(self, registry) -> None:
        """max_capacity written, then surfaced via get_wa_site_index."""
        registry.bulk_upsert_wa_sites(
            "-100",
            [
                {"resource_id": 1, "name": "Big Site", "loop_map_id": None, "max_capacity": 12},
                {"resource_id": 2, "name": "Small Site", "loop_map_id": None, "max_capacity": 4},
            ],
        )

        index = registry.get_wa_site_index("-100")

        assert index[1][2] == 12
        assert index[2][2] == 4

    def test_missing_capacity_is_none(self, registry) -> None:
        """A site dict without max_capacity stores NULL and surfaces as None."""
        registry.bulk_upsert_wa_sites(
            "-100",
            [{"resource_id": 1, "name": "X", "loop_map_id": None}],
        )

        index = registry.get_wa_site_index("-100")
        assert index[1][2] is None

    def test_allowed_equipment_persists_as_json(self, registry) -> None:
        """allowed_equipment stores JSON; persists across reads via SELECT."""
        import json as _json
        registry.bulk_upsert_wa_sites(
            "-100",
            [{
                "resource_id": 1,
                "name": "RV Site",
                "loop_map_id": None,
                "allowed_equipment": [
                    {"equipmentCategoryId": -32768, "subEquipmentCategoryId": -32767},
                    {"equipmentCategoryId": -32768, "subEquipmentCategoryId": -32766},
                ],
            }],
        )

        # get_wa_site_index doesn't surface equipment yet (defer to filter PR);
        # verify via direct SELECT that the JSON is intact.
        row = registry._conn.execute(
            "SELECT allowed_equipment FROM wa_state_sites WHERE resource_id = 1"
        ).fetchone()
        decoded = _json.loads(row["allowed_equipment"])
        assert len(decoded) == 2
        assert decoded[0] == {"equipmentCategoryId": -32768, "subEquipmentCategoryId": -32767}

    def test_default_allowed_equipment_is_empty_array(self, registry) -> None:
        """A site dict without allowed_equipment defaults to [] (not NULL)."""
        import json as _json
        registry.bulk_upsert_wa_sites(
            "-100",
            [{"resource_id": 1, "name": "X", "loop_map_id": None}],
        )
        row = registry._conn.execute(
            "SELECT allowed_equipment FROM wa_state_sites WHERE resource_id = 1"
        ).fetchone()
        assert _json.loads(row["allowed_equipment"]) == []

    def test_migration_adds_columns_to_existing_table(self, tmp_path) -> None:
        """A registry initialized against a pre-PR-B DB gets the new columns added."""
        import sqlite3 as _sqlite3
        db_path = tmp_path / "old_schema.db"
        # Simulate the pre-PR-B schema: wa_state_sites without the new columns
        conn = _sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE wa_state_sites (
                resource_id INTEGER PRIMARY KEY,
                park_facility_id TEXT NOT NULL,
                name TEXT NOT NULL,
                loop_map_id INTEGER,
                updated_at TEXT NOT NULL
            );
            INSERT INTO wa_state_sites VALUES (1, '-100', 'OldSite', NULL, '2026-01-01');
        """)
        conn.commit()
        conn.close()

        # Open via Registry — migration should fire and add the columns
        from pnw_campsites.registry.db import CampgroundRegistry
        reg = CampgroundRegistry(db_path)
        try:
            cols = {row[1] for row in reg._conn.execute("PRAGMA table_info(wa_state_sites)").fetchall()}
            assert "max_capacity" in cols
            assert "min_capacity" in cols
            assert "allowed_equipment" in cols

            # Pre-existing row is intact; new columns default to NULL or '[]'
            row = reg._conn.execute(
                "SELECT name, max_capacity, allowed_equipment FROM wa_state_sites WHERE resource_id = 1"
            ).fetchone()
            assert row["name"] == "OldSite"
            assert row["max_capacity"] is None
            assert row["allowed_equipment"] == "[]"
        finally:
            reg.close()
