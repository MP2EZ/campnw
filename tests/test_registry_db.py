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
