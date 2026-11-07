"""A provider failure must say what it was, both in the logs and in the warning.

In Nov 2026 every WA State Parks search in production came back
`error="unavailable"` while the same code worked locally and on staging. Nothing
in the logs said why, because:

  - `GoingToCampClient._fetch_map_availability` — the call every availability
    lookup makes — called `raise_for_status()` directly instead of going through
    `_get_sync`, so a WAF 403 surfaced as a generic HTTPError (warning kind
    "unavailable") rather than `WAFBlockedError` ("waf_blocked"), and a 429 was
    never `RateLimitedError`.
  - `SearchEngine._check_campground` caught that with a bare `except Exception`
    and returned `error="unavailable"` without logging the exception.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnw_campsites.providers.errors import RateLimitedError, WAFBlockedError
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.search.engine import SearchEngine, SearchQuery


def _client_returning(status: int) -> GoingToCampClient:
    client = GoingToCampClient()
    client._session = MagicMock()
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    client._session.get.return_value = resp
    return client


class TestAvailabilityEndpointClassifiesErrors:
    """`/api/availability/map` is the endpoint searches depend on."""

    def test_403_is_waf_blocked(self) -> None:
        client = _client_returning(403)
        with pytest.raises(WAFBlockedError):
            client._fetch_map_availability(1, date(2027, 6, 1), date(2027, 6, 30))

    def test_429_is_rate_limited(self) -> None:
        client = _client_returning(429)
        with pytest.raises(RateLimitedError):
            client._fetch_map_availability(1, date(2027, 6, 1), date(2027, 6, 30))

    def test_hits_the_availability_endpoint_with_its_params(self) -> None:
        client = GoingToCampClient()
        client._session = MagicMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"resourceAvailabilities": {}}
        client._session.get.return_value = resp

        client._fetch_map_availability(42, date(2027, 6, 1), date(2027, 6, 30))

        url = client._session.get.call_args.args[0]
        params = client._session.get.call_args.kwargs["params"]
        assert url.endswith("/api/availability/map")
        assert params["mapId"] == 42
        assert params["startDate"] == "2027-06-01"


class TestMetadataEndpointClassifiesRateLimit:
    def test_429_is_rate_limited(self) -> None:
        client = _client_returning(429)
        with pytest.raises(RateLimitedError):
            client._get_sync("/api/maps")


class TestEngineLogsUnclassifiedProviderErrors:
    def test_unavailable_result_logs_the_exception(self, caplog) -> None:
        gtc = MagicMock()
        gtc.get_availability = AsyncMock(
            side_effect=RuntimeError("curl: (28) Operation timed out")
        )
        engine = SearchEngine(MagicMock(), goingtocamp_client=gtc)
        campground = Campground(
            facility_id="-2147483646",
            name="Battle Ground Lake State Park",
            booking_system=BookingSystem.WA_STATE,
            state="WA",
        )

        with caplog.at_level(logging.WARNING, logger="pnw_campsites.search"):
            result = asyncio.run(
                engine._check_campground(
                    campground, date(2027, 6, 1), date(2027, 6, 30), SearchQuery(),
                )
            )

        assert result.error == "unavailable"
        logged = caplog.text
        assert "wa_state" in logged
        assert "-2147483646" in logged
        assert "RuntimeError" in logged
        assert "Operation timed out" in logged


class TestBlockedAtStartup:
    """The server builds its GoingToCampClient in the FastAPI lifespan.

    `__aenter__` loaded the park map index from `/api/maps` and let a 403
    propagate, so once Fly's egress IP was WAF-blocked, any restart or deploy
    would fail app startup outright and take every source down, not just WA.
    """

    def _blocked_session(self) -> MagicMock:
        session = MagicMock()
        resp = MagicMock(status_code=403)
        session.get.return_value = resp
        return session

    def test_enter_survives_a_blocked_index_load(self, monkeypatch) -> None:
        from pnw_campsites.providers import goingtocamp

        session = self._blocked_session()
        monkeypatch.setattr(
            goingtocamp.curl_requests, "Session", lambda **_: session,
        )

        async def enter() -> GoingToCampClient:
            return await GoingToCampClient().__aenter__()

        client = asyncio.run(enter())
        assert client._park_map_ids == {}

    def test_availability_reports_the_block_instead_of_empty_results(self) -> None:
        """An empty index must not read as "this park has no sites"."""
        client = GoingToCampClient()
        client._session = self._blocked_session()

        with pytest.raises(WAFBlockedError):
            client._get_availability_sync(
                -2147483646, date(2027, 6, 1), date(2027, 6, 30),
            )

    def test_index_loads_once_the_block_lifts(self) -> None:
        client = GoingToCampClient()
        client._session = MagicMock()
        maps = MagicMock(status_code=200)
        maps.json.return_value = [
            {"mapLinks": [{"resourceLocationId": -2147483646, "childMapId": 7}]},
        ]
        avail = MagicMock(status_code=200)
        avail.json.return_value = {"resourceAvailabilities": {"1": [0]}}
        client._session.get.side_effect = [maps, avail]

        result = client._get_availability_sync(
            -2147483646, date(2027, 6, 1), date(2027, 6, 1),
        )

        assert client._park_map_ids == {-2147483646: 7}
        assert list(result.campsites) == ["1"]

    def test_failed_index_load_is_not_retried_on_every_park(self) -> None:
        """A search fans out to ~75 WA parks at once; one blocked /api/maps
        call per park would hammer a WAF that is already blocking us."""
        client = GoingToCampClient()
        client._session = self._blocked_session()

        for _ in range(5):
            with pytest.raises(WAFBlockedError):
                client._get_availability_sync(
                    -2147483646, date(2027, 6, 1), date(2027, 6, 30),
                )

        assert client._session.get.call_count == 1
