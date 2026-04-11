"""Tests for drive_times table in CampgroundRegistry."""

import pytest

from pnw_campsites.registry.db import CampgroundRegistry


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "test.db"
    with CampgroundRegistry(db_path) as reg:
        yield reg


class TestDriveTimesTable:
    def test_upsert_and_query(self, registry):
        rows = [
            {
                "base_name": "seattle",
                "booking_system": "recgov",
                "facility_id": "232465",
                "drive_minutes": 170,
                "drive_miles": 174.2,
                "source": "mapbox",
                "computed_at": "2026-04-10T12:00:00",
            },
        ]
        count = registry.upsert_drive_times(rows)
        assert count == 1

        result = registry.get_drive_times_from_base("seattle")
        assert ("recgov", "232465") in result
        assert result[("recgov", "232465")] == 170

    def test_upsert_updates_existing(self, registry):
        row = {
            "base_name": "seattle",
            "booking_system": "recgov",
            "facility_id": "232465",
            "drive_minutes": 170,
            "drive_miles": 174.2,
            "source": "mapbox",
            "computed_at": "2026-04-10T12:00:00",
        }
        registry.upsert_drive_times([row])

        row["drive_minutes"] = 180
        row["computed_at"] = "2026-04-11T12:00:00"
        registry.upsert_drive_times([row])

        result = registry.get_drive_times_from_base("seattle")
        assert result[("recgov", "232465")] == 180

    def test_multiple_bases(self, registry):
        rows = [
            {
                "base_name": "seattle",
                "booking_system": "recgov",
                "facility_id": "100",
                "drive_minutes": 120,
                "drive_miles": 100.0,
                "source": "mapbox",
                "computed_at": "2026-04-10T12:00:00",
            },
            {
                "base_name": "portland",
                "booking_system": "recgov",
                "facility_id": "100",
                "drive_minutes": 200,
                "drive_miles": 180.0,
                "source": "mapbox",
                "computed_at": "2026-04-10T12:00:00",
            },
        ]
        registry.upsert_drive_times(rows)

        seattle = registry.get_drive_times_from_base("seattle")
        portland = registry.get_drive_times_from_base("portland")
        assert seattle[("recgov", "100")] == 120
        assert portland[("recgov", "100")] == 200

    def test_empty_base_returns_empty_dict(self, registry):
        result = registry.get_drive_times_from_base("nonexistent")
        assert result == {}

    def test_empty_upsert_returns_zero(self, registry):
        assert registry.upsert_drive_times([]) == 0

    def test_case_insensitive_base_lookup(self, registry):
        rows = [
            {
                "base_name": "seattle",
                "booking_system": "recgov",
                "facility_id": "100",
                "drive_minutes": 120,
                "drive_miles": 100.0,
                "source": "mapbox",
                "computed_at": "2026-04-10T12:00:00",
            },
        ]
        registry.upsert_drive_times(rows)
        result = registry.get_drive_times_from_base("Seattle")
        # base_name is stored lowercase, query lowercases
        assert ("recgov", "100") in result

    def test_bulk_upsert_many_rows(self, registry):
        rows = [
            {
                "base_name": "seattle",
                "booking_system": "recgov",
                "facility_id": str(i),
                "drive_minutes": 60 + i,
                "drive_miles": 50.0 + i,
                "source": "mapbox",
                "computed_at": "2026-04-10T12:00:00",
            }
            for i in range(100)
        ]
        count = registry.upsert_drive_times(rows)
        assert count == 100

        result = registry.get_drive_times_from_base("seattle")
        assert len(result) == 100
