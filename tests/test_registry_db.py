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
