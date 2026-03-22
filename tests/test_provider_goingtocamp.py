"""Tests for the GoingToCamp provider (WA State Parks API client)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from pnw_campsites.providers.errors import WAFBlockedError
from pnw_campsites.providers.goingtocamp import (
    _AVAILABILITY_MAP,
    CAMPSITE_CATEGORY,
    GROUP_CATEGORY,
    NON_GROUP_EQUIPMENT,
    OVERFLOW_CATEGORY,
    GoingToCampClient,
)
from pnw_campsites.registry.models import AvailabilityStatus


class TestAvailabilityMapping:
    """Test availability value → status mapping."""

    def test_availability_value_0_maps_to_available(self) -> None:
        """Availability value 0 → AVAILABLE."""
        assert _AVAILABILITY_MAP[0] == AvailabilityStatus.AVAILABLE

    def test_availability_value_1_maps_to_reserved(self) -> None:
        """Availability value 1 → RESERVED."""
        assert _AVAILABILITY_MAP[1] == AvailabilityStatus.RESERVED

    def test_availability_value_2_maps_to_closed(self) -> None:
        """Availability value 2 → CLOSED."""
        assert _AVAILABILITY_MAP[2] == AvailabilityStatus.CLOSED

    def test_availability_value_3_maps_to_not_reservable(self) -> None:
        """Availability value 3 → NOT_RESERVABLE."""
        assert _AVAILABILITY_MAP[3] == AvailabilityStatus.NOT_RESERVABLE

    def test_availability_value_4_maps_to_not_reservable_mgmt(self) -> None:
        """Availability value 4 → NOT_RESERVABLE_MGMT."""
        assert _AVAILABILITY_MAP[4] == AvailabilityStatus.NOT_RESERVABLE_MGMT

    def test_availability_value_5_maps_to_nyr(self) -> None:
        """Availability value 5 → NYR."""
        assert _AVAILABILITY_MAP[5] == AvailabilityStatus.NYR

    def test_all_availability_values_are_valid_statuses(self) -> None:
        """All mapped values are valid AvailabilityStatus enum members."""
        for status in _AVAILABILITY_MAP.values():
            assert isinstance(status, AvailabilityStatus)


class TestBuildCampsites:
    """Test _build_campsites transformation logic."""

    def test_single_site_single_day_available(self) -> None:
        """Single site, single day with availability 0 (available)."""
        client = GoingToCampClient()
        resources = {
            "2147482394": [{"availability": 0}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        assert len(result) == 1
        assert "2147482394" in result
        campsite = result["2147482394"]
        assert campsite.campsite_id == "2147482394"
        assert campsite.site == "WA-2147482394"
        assert campsite.loop == ""
        assert campsite.max_num_people == 8
        assert (
            campsite.availabilities["2026-06-01T00:00:00.000Z"]
            == AvailabilityStatus.AVAILABLE
        )

    def test_multiple_days_tracking(self) -> None:
        """Single site over multiple days with mixed availability."""
        client = GoingToCampClient()
        resources = {
            "123": [
                {"availability": 0},  # June 1: Available
                {"availability": 1},  # June 2: Reserved
                {"availability": 0},  # June 3: Available
            ],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 3)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["123"]
        assert (
            campsite.availabilities["2026-06-01T00:00:00.000Z"]
            == AvailabilityStatus.AVAILABLE
        )
        assert (
            campsite.availabilities["2026-06-02T00:00:00.000Z"]
            == AvailabilityStatus.RESERVED
        )
        assert (
            campsite.availabilities["2026-06-03T00:00:00.000Z"]
            == AvailabilityStatus.AVAILABLE
        )

    def test_unknown_availability_code_defaults_to_not_available(self) -> None:
        """Unknown availability code (not in _AVAILABILITY_MAP) → NOT_AVAILABLE."""
        client = GoingToCampClient()
        resources = {
            "999": [{"availability": 999}],  # unmapped value
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["999"]
        assert (
            campsite.availabilities["2026-06-01T00:00:00.000Z"]
            == AvailabilityStatus.NOT_AVAILABLE
        )

    def test_truncates_data_beyond_end_date(self) -> None:
        """Extra days in data beyond end_date are truncated."""
        client = GoingToCampClient()
        resources = {
            "123": [
                {"availability": 0},  # June 1
                {"availability": 1},  # June 2
                {"availability": 0},  # June 3
                {"availability": 1},  # June 4 (ignored)
                {"availability": 1},  # June 5 (ignored)
            ],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 3)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["123"]
        # Should only have 3 dates
        assert len(campsite.availabilities) == 3

    def test_max_num_people_defaults_to_8(self) -> None:
        """max_num_people defaults to 8 for all sites."""
        client = GoingToCampClient()
        resources = {
            "1": [{"availability": 0}],
            "2": [{"availability": 1}],
            "3": [{"availability": 2}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        for campsite in result.values():
            assert campsite.max_num_people == 8

    def test_loop_always_empty_string(self) -> None:
        """loop field is always an empty string."""
        client = GoingToCampClient()
        resources = {
            "1": [{"availability": 0}],
            "2": [{"availability": 0}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        for campsite in result.values():
            assert campsite.loop == ""

    def test_site_format_wa_prefix(self) -> None:
        """site field formatted as WA-{resource_id}."""
        client = GoingToCampClient()
        resources = {
            "2147482394": [{"availability": 0}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["2147482394"]
        assert campsite.site == "WA-2147482394"

    def test_multiple_sites_all_transformed(self) -> None:
        """Multiple resource IDs all transformed correctly."""
        client = GoingToCampClient()
        resources = {
            "res1": [{"availability": 0}],
            "res2": [{"availability": 1}],
            "res3": [{"availability": 2}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        assert len(result) == 3
        assert all(res_id in result for res_id in ["res1", "res2", "res3"])

    def test_dict_vs_scalar_availability_value(self) -> None:
        """Handles both dict {'availability': int} and scalar int formats."""
        client = GoingToCampClient()
        resources = {
            "dict_format": [{"availability": 0}, {"availability": 1}],
            "scalar_format": [0, 1],  # scalar values directly
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 2)

        result = client._build_campsites(resources, start_date, end_date)

        assert len(result) == 2
        # Both formats should produce same status mapping
        dict_site = result["dict_format"]
        scalar_site = result["scalar_format"]
        assert (
            dict_site.availabilities["2026-06-01T00:00:00.000Z"]
            == scalar_site.availabilities["2026-06-01T00:00:00.000Z"]
        )


class TestCollectResourcesDepthLimit:
    """Test _collect_resources depth limit (max depth 5)."""

    def test_depth_zero_allowed(self) -> None:
        """Depth 0 → allowed, processes normally."""
        client = GoingToCampClient()
        out: dict[str, list[dict]] = {}

        # Patch the sync methods to avoid real HTTP calls
        with patch.object(
            client,
            "_fetch_map_availability",
            return_value={"resourceAvailabilities": {}, "mapLinkAvailabilities": {}},
        ) as mock_fetch:
            client._collect_resources(
                map_id=1,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                out=out,
                depth=0,
            )
            # Should call _fetch_map_availability (no exception)
            mock_fetch.assert_called_once()

    def test_depth_five_allowed(self) -> None:
        """Depth 5 (limit) → allowed, processes normally."""
        client = GoingToCampClient()
        out: dict[str, list[dict]] = {}

        with patch.object(
            client,
            "_fetch_map_availability",
            return_value={"resourceAvailabilities": {}, "mapLinkAvailabilities": {}},
        ) as mock_fetch:
            client._collect_resources(
                map_id=1,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                out=out,
                depth=5,
            )
            mock_fetch.assert_called_once()

    def test_depth_six_stopped(self) -> None:
        """Depth 6 (over limit) → returns immediately without fetching."""
        client = GoingToCampClient()
        out: dict[str, list[dict]] = {}

        with patch.object(client, "_fetch_map_availability") as mock_fetch:
            client._collect_resources(
                map_id=1,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                out=out,
                depth=6,
            )

            # Should NOT call _fetch_map_availability
            mock_fetch.assert_not_called()

    def test_depth_limit_prevents_infinite_recursion(self) -> None:
        """Depth limit prevents infinite recursion in circular map links."""
        client = GoingToCampClient()
        out: dict[str, list[dict]] = {}

        # Simulate circular map link: mapLinkAvailabilities contains self-reference
        def mock_fetch(map_id: int, start_date: date, end_date: date) -> dict:
            return {
                "resourceAvailabilities": {},
                "mapLinkAvailabilities": {map_id: {}},  # circular ref to same map
            }

        with patch.object(
            client, "_fetch_map_availability", side_effect=mock_fetch
        ) as mock_method:
            # Should complete without infinite recursion
            client._collect_resources(
                map_id=100,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                out=out,
                depth=0,
            )

            # _fetch_map_availability should be called multiple times (up to depth limit)
            assert mock_method.call_count >= 1


class TestGetSyncErrorHandling:
    """Test _get_sync error handling and retry behavior."""

    def test_403_response_raises_waf_blocked_error(self) -> None:
        """403 status code → WAFBlockedError."""
        client = GoingToCampClient()
        client._session = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 403
        client._session.get.return_value = mock_response

        with pytest.raises(WAFBlockedError, match="WAF blocked"):
            client._get_sync("/api/test")

    def test_500_error_retries_once(self) -> None:
        """500 error on first attempt → retries; second attempt success."""
        client = GoingToCampClient()
        client._session = MagicMock()

        # First call returns 500, second returns 200
        response_500 = MagicMock()
        response_500.status_code = 500
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": "success"}

        client._session.get.side_effect = [response_500, response_200]

        result = client._get_sync("/api/test")

        assert result == {"data": "success"}
        assert client._session.get.call_count == 2

    def test_non_500_error_not_retried(self) -> None:
        """Non-500 error (e.g., 404) → no retry, raise immediately."""
        client = GoingToCampClient()
        client._session = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = RuntimeError("404 Not Found")
        client._session.get.return_value = mock_response

        with pytest.raises(RuntimeError):
            client._get_sync("/api/test")

        # Should be called only once (no retry)
        assert client._session.get.call_count == 1

    def test_500_on_both_attempts_raises(self) -> None:
        """500 on both attempts → raise after retry."""
        client = GoingToCampClient()
        client._session = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = RuntimeError("500 Server Error")

        client._session.get.side_effect = [mock_response, mock_response]

        with pytest.raises(RuntimeError):
            client._get_sync("/api/test")

        assert client._session.get.call_count == 2


class TestCategoryConstants:
    """Test that category IDs are defined and have expected values."""

    def test_campsite_category_defined(self) -> None:
        """CAMPSITE_CATEGORY constant defined."""
        assert CAMPSITE_CATEGORY == -2147483648

    def test_group_category_defined(self) -> None:
        """GROUP_CATEGORY constant defined."""
        assert GROUP_CATEGORY == -2147483643

    def test_overflow_category_defined(self) -> None:
        """OVERFLOW_CATEGORY constant defined."""
        assert OVERFLOW_CATEGORY == -2147483647

    def test_non_group_equipment_defined(self) -> None:
        """NON_GROUP_EQUIPMENT constant defined."""
        assert NON_GROUP_EQUIPMENT == -32768


class TestCampsiteDataFields:
    """Test CampsiteAvailability field values set by _build_campsites."""

    def test_campsite_type_always_standard(self) -> None:
        """campsite_type always set to 'STANDARD'."""
        client = GoingToCampClient()
        resources = {
            "1": [{"availability": 0}],
            "2": [{"availability": 1}],
        }
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        for campsite in result.values():
            assert campsite.campsite_type == "STANDARD"

    def test_type_of_use_always_overnight(self) -> None:
        """type_of_use always set to 'Overnight'."""
        client = GoingToCampClient()
        resources = {"1": [{"availability": 0}]}
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["1"]
        assert campsite.type_of_use == "Overnight"

    def test_min_num_people_always_zero(self) -> None:
        """min_num_people always set to 0."""
        client = GoingToCampClient()
        resources = {"1": [{"availability": 0}]}
        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 1)

        result = client._build_campsites(resources, start_date, end_date)

        campsite = result["1"]
        assert campsite.min_num_people == 0
