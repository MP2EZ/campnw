"""Tests for RecGov provider — RIDB metadata and availability APIs."""

from datetime import date

import pytest
import respx
from httpx import Response

from pnw_campsites.providers.errors import FacilityNotFoundError, RateLimitedError
from pnw_campsites.providers.recgov import (
    AVAILABILITY_BASE,
    BROWSER_USER_AGENT,
    RIDB_BASE,
    RecGovClient,
)
from pnw_campsites.registry.models import AvailabilityStatus

# -----------------------------------------------------------------------
# Availability endpoint tests (get_availability)
# -----------------------------------------------------------------------


@respx.mock
async def test_get_availability_successful_response():
    """Successful response parses CampgroundAvailability correctly."""
    facility_id = "232465"
    month = date(2026, 6, 15)
    start_date = "2026-06-01T00:00:00.000Z"

    response_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                    "2026-06-02T00:00:00.000Z": "Reserved",
                    "2026-06-03T00:00:00.000Z": "Available",
                },
            }
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability(facility_id, month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 1
    assert "1234567" in result.campsites
    site = result.campsites["1234567"]
    assert site.site == "A001"
    assert site.loop == "Loop A"
    assert site.campsite_type == "STANDARD NONELECTRIC"
    assert len(site.availabilities) == 3
    assert site.availabilities["2026-06-01T00:00:00.000Z"] == AvailabilityStatus.AVAILABLE


@respx.mock
async def test_get_availability_404_raises_facility_not_found():
    """404 response raises FacilityNotFoundError."""
    facility_id = "999999"
    month = date(2026, 6, 15)
    start_date = "2026-06-01T00:00:00.000Z"

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    ).mock(return_value=Response(404, json={"error": "Not found"}))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        with pytest.raises(FacilityNotFoundError) as exc_info:
            await client.get_availability(facility_id, month)
    assert "999999" in str(exc_info.value)


@respx.mock
async def test_get_availability_429_then_200_retry_succeeds():
    """429 on first attempt retries and returns result on success."""
    facility_id = "232465"
    month = date(2026, 6, 15)
    start_date = "2026-06-01T00:00:00.000Z"

    response_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                },
            }
        }
    }

    route = respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    )
    route.side_effect = [
        Response(429, json={"error": "Rate limited"}),
        Response(200, json=response_data),
    ]

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability(facility_id, month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 1


@respx.mock
async def test_get_availability_429_twice_raises_rate_limited():
    """429 on both attempts raises RateLimitedError."""
    facility_id = "232465"
    month = date(2026, 6, 15)
    start_date = "2026-06-01T00:00:00.000Z"

    route = respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    )
    route.side_effect = [
        Response(429, json={"error": "Rate limited"}),
        Response(429, json={"error": "Rate limited"}),
    ]

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        with pytest.raises(RateLimitedError) as exc_info:
            await client.get_availability(facility_id, month)
    assert "232465" in str(exc_info.value)


@respx.mock
async def test_get_availability_5xx_then_200_retry_succeeds():
    """5xx on first attempt retries and returns result on success."""
    facility_id = "232465"
    month = date(2026, 6, 15)
    start_date = "2026-06-01T00:00:00.000Z"

    response_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                },
            }
        }
    }

    route = respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    )
    route.side_effect = [
        Response(503, json={"error": "Service unavailable"}),
        Response(200, json=response_data),
    ]

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability(facility_id, month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 1


@respx.mock
async def test_get_availability_month_date_normalization():
    """Any day of month is normalized to 1st."""
    facility_id = "232465"
    response_data = {"campsites": {}}

    # Request with day=15 should hit API with day=1
    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-06-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        # Pass date(2026, 6, 15) but it should hit with day=1
        result = await client.get_availability(facility_id, date(2026, 6, 15))

    assert result.facility_id == facility_id
    assert len(result.campsites) == 0


@respx.mock
async def test_get_availability_empty_campsites():
    """Empty campsites dict returns CampgroundAvailability with no sites."""
    facility_id = "232465"
    month = date(2026, 6, 1)
    start_date = "2026-06-01T00:00:00.000Z"

    response_data = {"campsites": {}}

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability(facility_id, month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 0


@respx.mock
async def test_get_availability_multiple_campsites():
    """Multiple campsites in response all included."""
    facility_id = "232465"
    month = date(2026, 6, 1)
    start_date = "2026-06-01T00:00:00.000Z"

    response_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {"2026-06-01T00:00:00.000Z": "Available"},
            },
            "1234568": {
                "campsite_id": "1234568",
                "site": "A002",
                "loop": "Loop A",
                "campsite_type": "STANDARD ELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 8,
                "availabilities": {"2026-06-01T00:00:00.000Z": "Reserved"},
            },
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": start_date},
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability(facility_id, month)

    assert len(result.campsites) == 2
    assert "1234567" in result.campsites
    assert "1234568" in result.campsites


# -----------------------------------------------------------------------
# Availability range tests (get_availability_range)
# -----------------------------------------------------------------------


@respx.mock
async def test_get_availability_range_single_month():
    """Single month range calls get_availability once."""
    facility_id = "232465"
    start_month = date(2026, 6, 1)
    end_month = date(2026, 6, 30)

    response_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                    "2026-06-02T00:00:00.000Z": "Reserved",
                },
            }
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-06-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability_range(facility_id, start_month, end_month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 1


@respx.mock
async def test_get_availability_range_two_months():
    """Two month range fetches both months."""
    facility_id = "232465"
    start_month = date(2026, 6, 1)
    end_month = date(2026, 7, 1)

    june_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                },
            }
        }
    }

    july_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-07-01T00:00:00.000Z": "Reserved",
                },
            }
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-06-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=june_data))

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-07-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=july_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability_range(facility_id, start_month, end_month)

    assert result.facility_id == facility_id
    assert len(result.campsites) == 1
    # Availabilities should be merged
    site = result.campsites["1234567"]
    assert len(site.availabilities) == 2
    assert "2026-06-01T00:00:00.000Z" in site.availabilities
    assert "2026-07-01T00:00:00.000Z" in site.availabilities


@respx.mock
async def test_get_availability_range_same_site_different_months():
    """Same campsite in multiple months has availabilities merged."""
    facility_id = "232465"
    start_month = date(2026, 6, 15)
    end_month = date(2026, 7, 15)

    june_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-15T00:00:00.000Z": "Available",
                    "2026-06-16T00:00:00.000Z": "Available",
                },
            }
        }
    }

    july_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-07-10T00:00:00.000Z": "Reserved",
                    "2026-07-11T00:00:00.000Z": "Available",
                },
            }
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-06-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=june_data))

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-07-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=july_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability_range(facility_id, start_month, end_month)

    site = result.campsites["1234567"]
    assert len(site.availabilities) == 4


@respx.mock
async def test_get_availability_range_different_sites_per_month():
    """Different sites per month all appear in merged result."""
    facility_id = "232465"
    start_month = date(2026, 6, 1)
    end_month = date(2026, 7, 1)

    june_data = {
        "campsites": {
            "1234567": {
                "campsite_id": "1234567",
                "site": "A001",
                "loop": "Loop A",
                "campsite_type": "STANDARD NONELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 6,
                "availabilities": {
                    "2026-06-01T00:00:00.000Z": "Available",
                },
            }
        }
    }

    july_data = {
        "campsites": {
            "1234568": {
                "campsite_id": "1234568",
                "site": "A002",
                "loop": "Loop A",
                "campsite_type": "STANDARD ELECTRIC",
                "type_of_use": "Overnight",
                "min_num_people": 0,
                "max_num_people": 8,
                "availabilities": {
                    "2026-07-01T00:00:00.000Z": "Available",
                },
            }
        }
    }

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-06-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=june_data))

    respx.get(
        f"{AVAILABILITY_BASE}/{facility_id}/month",
        params={"start_date": "2026-07-01T00:00:00.000Z"},
    ).mock(return_value=Response(200, json=july_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        result = await client.get_availability_range(facility_id, start_month, end_month)

    assert len(result.campsites) == 2
    assert "1234567" in result.campsites
    assert "1234568" in result.campsites


# -----------------------------------------------------------------------
# RIDB metadata tests
# -----------------------------------------------------------------------


@respx.mock
async def test_get_facilities_returns_parsed_list():
    """get_facilities parses RECDATA array and returns (facilities, total)."""
    response_data = {
        "METADATA": {
            "RESULTS": {
                "TOTAL_COUNT": 2,
            }
        },
        "RECDATA": [
            {
                "FacilityID": "232465",
                "FacilityName": "Ohanapecosh",
                "FacilityTypeDescription": "Campground",
                "FacilityLatitude": 46.75,
                "FacilityLongitude": -121.80,
                "ParentOrgID": "12345",
                "ParentRecAreaID": "67890",
                "FacilityDescription": "Mountain campground",
                "Reservable": True,
                "Enabled": True,
            },
            {
                "FacilityID": "232466",
                "FacilityName": "Sunshine Point",
                "FacilityTypeDescription": "Campground",
                "FacilityLatitude": 46.71,
                "FacilityLongitude": -121.82,
                "ParentOrgID": "12345",
                "ParentRecAreaID": "67890",
                "FacilityDescription": "Another campground",
                "Reservable": True,
                "Enabled": True,
            },
        ],
    }

    respx.get(f"{RIDB_BASE}/facilities").mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        facilities, total = await client.get_facilities(state="WA")

    assert len(facilities) == 2
    assert total == 2
    assert facilities[0].facility_id == "232465"
    assert facilities[0].facility_name == "Ohanapecosh"
    assert facilities[1].facility_id == "232466"


@respx.mock
async def test_get_all_facilities_paginates():
    """get_all_facilities paginates through multiple pages."""
    page1_data = {
        "METADATA": {
            "RESULTS": {
                "TOTAL_COUNT": 125,
            }
        },
        "RECDATA": [
            {
                "FacilityID": f"10{i}",
                "FacilityName": f"Facility {i}",
                "FacilityTypeDescription": "Campground",
                "FacilityLatitude": 46.0 + i * 0.1,
                "FacilityLongitude": -121.0 + i * 0.1,
                "ParentOrgID": "12345",
                "ParentRecAreaID": "67890",
                "FacilityDescription": "",
                "Reservable": True,
                "Enabled": True,
            }
            for i in range(50)
        ],
    }

    page2_data = {
        "METADATA": {
            "RESULTS": {
                "TOTAL_COUNT": 125,
            }
        },
        "RECDATA": [
            {
                "FacilityID": f"10{i}",
                "FacilityName": f"Facility {i}",
                "FacilityTypeDescription": "Campground",
                "FacilityLatitude": 46.0 + i * 0.1,
                "FacilityLongitude": -121.0 + i * 0.1,
                "ParentOrgID": "12345",
                "ParentRecAreaID": "67890",
                "FacilityDescription": "",
                "Reservable": True,
                "Enabled": True,
            }
            for i in range(50, 100)
        ],
    }

    page3_data = {
        "METADATA": {
            "RESULTS": {
                "TOTAL_COUNT": 125,
            }
        },
        "RECDATA": [
            {
                "FacilityID": f"10{i}",
                "FacilityName": f"Facility {i}",
                "FacilityTypeDescription": "Campground",
                "FacilityLatitude": 46.0 + i * 0.1,
                "FacilityLongitude": -121.0 + i * 0.1,
                "ParentOrgID": "12345",
                "ParentRecAreaID": "67890",
                "FacilityDescription": "",
                "Reservable": True,
                "Enabled": True,
            }
            for i in range(100, 125)
        ],
    }

    route = respx.get(f"{RIDB_BASE}/facilities")
    route.side_effect = [
        Response(200, json=page1_data),
        Response(200, json=page2_data),
        Response(200, json=page3_data),
    ]

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        facilities = await client.get_all_facilities(state="WA")

    assert len(facilities) == 125


@respx.mock
async def test_get_facility_campsites_returns_list():
    """get_facility_campsites returns campsite list from RECDATA."""
    facility_id = "232465"
    response_data = {
        "RECDATA": [
            {
                "FacilitySiteID": "1234567",
                "SiteName": "A001",
                "Loop": "Loop A",
                "SiteTypeDescription": "STANDARD NONELECTRIC",
            },
            {
                "FacilitySiteID": "1234568",
                "SiteName": "A002",
                "Loop": "Loop A",
                "SiteTypeDescription": "STANDARD ELECTRIC",
            },
        ],
    }

    respx.get(f"{RIDB_BASE}/facilities/{facility_id}/campsites").mock(
        return_value=Response(200, json=response_data)
    )

    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        campsites = await client.get_facility_campsites(facility_id)

    assert len(campsites) == 2
    assert campsites[0]["FacilitySiteID"] == "1234567"
    assert campsites[1]["FacilitySiteID"] == "1234568"


# -----------------------------------------------------------------------
# Client lifecycle tests
# -----------------------------------------------------------------------


async def test_client_context_manager():
    """Client context manager properly initializes and closes."""
    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        assert client._ridb_client is not None
        assert client._availability_client is not None

    # Clients should be closed after exiting context
    # (httpx.AsyncClient doesn't raise on double-close, so we just verify it doesn't crash)


async def test_client_has_browser_user_agent():
    """Client headers include browser-like User-Agent."""
    client = RecGovClient(ridb_api_key="test-key")
    async with client:
        headers = client._availability_client.headers
        assert "User-Agent" in headers
        assert headers["User-Agent"] == BROWSER_USER_AGENT
        assert "Chrome" in headers["User-Agent"]


@respx.mock
async def test_ridb_client_includes_api_key_header():
    """RIDB client sends API key in headers."""
    response_data = {
        "METADATA": {"RESULTS": {"TOTAL_COUNT": 0}},
        "RECDATA": [],
    }

    # Match request with apikey header
    respx.get(
        f"{RIDB_BASE}/facilities",
    ).mock(return_value=Response(200, json=response_data))

    client = RecGovClient(ridb_api_key="my-test-key-12345")
    async with client:
        await client.get_facilities(state="WA")

    # Verify the request had the correct API key
    assert respx.calls.last.request.headers["apikey"] == "my-test-key-12345"
