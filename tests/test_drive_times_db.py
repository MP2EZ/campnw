"""Tests for drive_times table in CampgroundRegistry."""


def _row(**overrides) -> dict:
    row = {
        "base_name": "seattle",
        "booking_system": "recgov",
        "facility_id": "232465",
        "drive_minutes": 170,
        "drive_miles": 174.2,
        "source": "mapbox",
        "computed_at": "2026-04-10T12:00:00",
    }
    row.update(overrides)
    return row


class TestDriveTimesTable:
    def test_upsert_and_query(self, registry):
        assert registry.upsert_drive_times([_row()]) == 1

        result = registry.get_drive_times_from_base("seattle")
        assert result[("recgov", "232465")] == 170

    def test_upsert_updates_existing(self, registry):
        row = _row()
        registry.upsert_drive_times([row])

        row["drive_minutes"] = 180
        row["computed_at"] = "2026-04-11T12:00:00"
        registry.upsert_drive_times([row])

        result = registry.get_drive_times_from_base("seattle")
        assert result[("recgov", "232465")] == 180

    def test_multiple_bases(self, registry):
        registry.upsert_drive_times([
            _row(facility_id="100", drive_minutes=120),
            _row(base_name="portland", facility_id="100", drive_minutes=200),
        ])

        seattle = registry.get_drive_times_from_base("seattle")
        portland = registry.get_drive_times_from_base("portland")
        assert seattle[("recgov", "100")] == 120
        assert portland[("recgov", "100")] == 200

    def test_empty_base_returns_empty_dict(self, registry):
        assert registry.get_drive_times_from_base("nonexistent") == {}

    def test_empty_upsert_returns_zero(self, registry):
        assert registry.upsert_drive_times([]) == 0

    def test_case_insensitive_base_lookup(self, registry):
        registry.upsert_drive_times([_row(facility_id="100")])
        # base_name is stored lowercase, query lowercases
        assert ("recgov", "100") in registry.get_drive_times_from_base("Seattle")
