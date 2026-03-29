"""Tests for the ReserveAmerica provider (Oregon State Parks)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from pnw_campsites.providers.errors import (
    FacilityNotFoundError,
    RateLimitedError,
    WAFBlockedError,
)
from pnw_campsites.providers.reserveamerica import (
    ReserveAmericaClient,
    _extract_records,
    _get_attribute_value,
    _parse_availability_grid,
    _record_to_campsite,
    _STATUS_MAP,
)
from pnw_campsites.registry.models import AvailabilityStatus


# ---------------------------------------------------------------------------
# Fixtures — sample RA data structures
# ---------------------------------------------------------------------------


def _make_record(
    site_id: int = 42057,
    name: str = "B01",
    loop: str = "B",
    prod_grp: str = "STANDARD",
    grid: list[dict] | None = None,
    max_people: str = "8",
    min_people: str = "1",
) -> dict:
    """Build a minimal RA record for testing."""
    if grid is None:
        grid = [
            {"date": "2026-07-01", "inventoryCount": 1, "status": "AVAILABLE"},
            {"date": "2026-07-02", "inventoryCount": 0, "status": "RESERVED"},
        ]
    return {
        "id": site_id,
        "prodGrpId": 114,
        "prodInfo": {"lineOfBusiness": "CAMPING", "typeOfUse": "NIGHTLY", "typeOfUseLabel": "Overnight"},
        "prodGrpName": prod_grp,
        "name": name,
        "details": {
            "siteCode": name,
            "loopName": loop,
            "attributes": [
                {"id": 111, "name": "Minimum Number of People", "value": [min_people]},
                {"id": 12, "name": "Maximum Number of People", "value": [max_people]},
            ],
        },
        "reservableType": None,
        "available": True,
        "bookingStatus": None,
        "availableSites": 1,
        "availabilityGrid": grid,
        "geolocated": True,
        "matchedCartItemID": None,
    }


def _make_redux_html(records: list[dict], total_records: int = 20) -> str:
    """Build a minimal HTML page with embedded Redux state."""
    state = {
        "application": {"theme": "default"},
        "backend": {
            "productSearch": {
                "searchResults": {
                    "totalRecords": total_records,
                    "totalPages": 1,
                    "startIndex": 0,
                    "endIndex": len(records),
                    "records": records,
                    "summary": {
                        "atLeastOneSiteAvailable": any(r.get("available") for r in records),
                    },
                }
            },
            "facility": {
                "facility": {
                    "id": 402178,
                    "name": "Test State Park",
                    "contrCode": "OR",
                    "coordinates": {"latitude": 46.2, "longitude": -123.97},
                }
            },
        },
    }
    return f'<html><script>{json.dumps(state)}</script></html>'


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


class TestStatusMapping:
    """Test RA status string → AvailabilityStatus mapping."""

    def test_available_maps_correctly(self) -> None:
        assert _STATUS_MAP["AVAILABLE"] == AvailabilityStatus.AVAILABLE

    def test_reserved_maps_correctly(self) -> None:
        assert _STATUS_MAP["RESERVED"] == AvailabilityStatus.RESERVED

    def test_not_available_maps_correctly(self) -> None:
        assert _STATUS_MAP["NOT_AVAILABLE"] == AvailabilityStatus.NOT_AVAILABLE

    def test_walk_up_maps_to_open(self) -> None:
        assert _STATUS_MAP["WALK_UP"] == AvailabilityStatus.OPEN

    def test_all_statuses_are_valid_enum(self) -> None:
        for status in _STATUS_MAP.values():
            assert isinstance(status, AvailabilityStatus)


# ---------------------------------------------------------------------------
# Availability grid parsing
# ---------------------------------------------------------------------------


class TestParseAvailabilityGrid:
    """Test _parse_availability_grid."""

    def test_parses_mixed_statuses(self) -> None:
        grid = [
            {"date": "2026-07-01", "status": "AVAILABLE"},
            {"date": "2026-07-02", "status": "RESERVED"},
            {"date": "2026-07-03", "status": "NOT_AVAILABLE"},
        ]
        result = _parse_availability_grid(grid)

        assert result["2026-07-01T00:00:00.000Z"] == AvailabilityStatus.AVAILABLE
        assert result["2026-07-02T00:00:00.000Z"] == AvailabilityStatus.RESERVED
        assert result["2026-07-03T00:00:00.000Z"] == AvailabilityStatus.NOT_AVAILABLE

    def test_unknown_status_defaults_to_not_available(self) -> None:
        grid = [{"date": "2026-07-01", "status": "SOME_NEW_STATUS"}]
        result = _parse_availability_grid(grid)
        assert result["2026-07-01T00:00:00.000Z"] == AvailabilityStatus.NOT_AVAILABLE

    def test_empty_grid_returns_empty_dict(self) -> None:
        assert _parse_availability_grid([]) == {}

    def test_missing_date_skipped(self) -> None:
        grid = [
            {"date": "2026-07-01", "status": "AVAILABLE"},
            {"status": "RESERVED"},  # no date key
        ]
        result = _parse_availability_grid(grid)
        assert len(result) == 1

    def test_iso_key_format(self) -> None:
        """Date keys are formatted as ISO datetime with Z suffix."""
        grid = [{"date": "2026-07-15", "status": "AVAILABLE"}]
        result = _parse_availability_grid(grid)
        assert "2026-07-15T00:00:00.000Z" in result


# ---------------------------------------------------------------------------
# Attribute extraction
# ---------------------------------------------------------------------------


class TestGetAttributeValue:
    """Test _get_attribute_value."""

    def test_extracts_max_people(self) -> None:
        record = _make_record(max_people="10")
        assert _get_attribute_value(record, 12) == "10"

    def test_extracts_min_people(self) -> None:
        record = _make_record(min_people="2")
        assert _get_attribute_value(record, 111) == "2"

    def test_missing_attribute_returns_none(self) -> None:
        record = _make_record()
        assert _get_attribute_value(record, 9999) is None

    def test_empty_attributes_returns_none(self) -> None:
        record = {"details": {"attributes": []}}
        assert _get_attribute_value(record, 12) is None


# ---------------------------------------------------------------------------
# Record to campsite conversion
# ---------------------------------------------------------------------------


class TestRecordToCampsite:
    """Test _record_to_campsite."""

    def test_basic_conversion(self) -> None:
        record = _make_record(site_id=42057, name="A01", loop="A", max_people="6")
        avail = {"2026-07-01T00:00:00.000Z": AvailabilityStatus.AVAILABLE}
        result = _record_to_campsite(record, avail)

        assert result.campsite_id == "42057"
        assert result.site == "A01"
        assert result.loop == "A"
        assert result.max_num_people == 6
        assert result.type_of_use == "Overnight"
        assert result.availabilities == avail

    def test_defaults_when_attributes_missing(self) -> None:
        record = {
            "id": 1,
            "name": "X01",
            "prodGrpName": "PRIMITIVE",
            "prodInfo": {"typeOfUseLabel": "Overnight"},
            "details": {"loopName": "", "attributes": []},
        }
        result = _record_to_campsite(record, {})
        assert result.min_num_people == 0
        assert result.max_num_people == 8  # default
        assert result.campsite_type == "PRIMITIVE"


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


class TestExtractRecords:
    """Test _extract_records HTML → records parsing."""

    def test_extracts_records_from_valid_html(self) -> None:
        records_data = [_make_record(), _make_record(site_id=42058, name="B02")]
        html = _make_redux_html(records_data, total_records=520)

        records, total = _extract_records(html)
        assert len(records) == 2
        assert total == 520

    def test_no_redux_state_returns_empty(self) -> None:
        html = "<html><body>No data here</body></html>"
        records, total = _extract_records(html)
        assert records == []
        assert total == 0

    def test_malformed_json_returns_empty(self) -> None:
        html = '<html><script>{"application":{bad json}</script></html>'
        records, total = _extract_records(html)
        assert records == []
        assert total == 0


# ---------------------------------------------------------------------------
# Client error handling
# ---------------------------------------------------------------------------


class TestClientErrors:
    """Test ReserveAmericaClient error handling in _fetch_window."""

    def test_403_raises_waf_blocked(self) -> None:
        client = ReserveAmericaClient()
        client._session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        client._session.get.return_value = mock_resp

        with pytest.raises(WAFBlockedError):
            client._fetch_window("402178", "test-park", "OR", date(2026, 7, 1), date(2026, 7, 14))

    def test_404_raises_facility_not_found(self) -> None:
        client = ReserveAmericaClient()
        client._session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._session.get.return_value = mock_resp

        with pytest.raises(FacilityNotFoundError):
            client._fetch_window("999999", "fake-park", "OR", date(2026, 7, 1), date(2026, 7, 14))

    def test_429_raises_rate_limited(self) -> None:
        client = ReserveAmericaClient()
        client._session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        client._session.get.return_value = mock_resp

        with pytest.raises(RateLimitedError):
            client._fetch_window("402178", "test-park", "OR", date(2026, 7, 1), date(2026, 7, 14))

    def test_500_retries_then_succeeds(self) -> None:
        client = ReserveAmericaClient()
        client._session = MagicMock()

        mock_500 = MagicMock()
        mock_500.status_code = 500

        records = [_make_record()]
        html = _make_redux_html(records, total_records=1)
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = html

        client._session.get.side_effect = [mock_500, mock_200]

        records_out, total = client._fetch_window(
            "402178", "test-park", "OR", date(2026, 7, 1), date(2026, 7, 14),
        )
        assert len(records_out) == 1
        assert client._session.get.call_count == 2


# ---------------------------------------------------------------------------
# Date windowing
# ---------------------------------------------------------------------------


class TestDateWindowing:
    """Test that _get_availability_sync breaks date ranges into 14-day windows."""

    @patch("pnw_campsites.providers.reserveamerica.time.sleep")
    def test_single_window_no_split(self, mock_sleep: MagicMock) -> None:
        """Date range <= 14 days makes one request."""
        client = ReserveAmericaClient()
        records = [_make_record()]
        html = _make_redux_html(records)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html

        client._session = MagicMock()
        client._session.get.return_value = mock_resp

        result = client._get_availability_sync(
            "402178", "test-park", "OR", date(2026, 7, 1), date(2026, 7, 14),
        )

        assert client._session.get.call_count == 1
        assert len(result.campsites) == 1
        mock_sleep.assert_not_called()

    @patch("pnw_campsites.providers.reserveamerica.time.sleep")
    def test_two_windows_for_20_days(self, mock_sleep: MagicMock) -> None:
        """20-day range needs 2 requests (14 + 6 days)."""
        client = ReserveAmericaClient()

        grid1 = [{"date": f"2026-07-{d:02d}", "status": "AVAILABLE"} for d in range(1, 15)]
        grid2 = [{"date": f"2026-07-{d:02d}", "status": "AVAILABLE"} for d in range(15, 21)]

        html1 = _make_redux_html([_make_record(grid=grid1)])
        html2 = _make_redux_html([_make_record(grid=grid2)])

        mock_resp1 = MagicMock(status_code=200, text=html1)
        mock_resp2 = MagicMock(status_code=200, text=html2)

        client._session = MagicMock()
        client._session.get.side_effect = [mock_resp1, mock_resp2]

        result = client._get_availability_sync(
            "402178", "test-park", "OR", date(2026, 7, 1), date(2026, 7, 20),
        )

        assert client._session.get.call_count == 2
        # Should have merged availability from both windows
        campsite = list(result.campsites.values())[0]
        assert len(campsite.availabilities) == 20
        mock_sleep.assert_called_once_with(1.0)
