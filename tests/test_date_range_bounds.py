"""Search date ranges are bounded before any provider is called.

An unbounded range fans out one rec.gov request per month (audit SEC-01/02):
a 10-year span from an anonymous request was thousands of upstream calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.search.engine import (
    MAX_DAYS_AHEAD,
    MAX_SPAN_DAYS,
    DateRangeError,
    SearchEngine,
    check_date_range,
)

TODAY = date(2026, 11, 22)


class TestCheckDateRange:
    def test_accepts_a_normal_month(self):
        check_date_range(date(2026, 12, 1), date(2026, 12, 31), today=TODAY)

    def test_accepts_the_longest_span(self):
        start = date(2027, 1, 1)
        check_date_range(start, start + timedelta(days=MAX_SPAN_DAYS), today=TODAY)

    def test_accepts_a_single_night(self):
        check_date_range(date(2026, 12, 5), date(2026, 12, 5), today=TODAY)

    def test_rejects_end_before_start(self):
        with pytest.raises(DateRangeError):
            check_date_range(date(2026, 12, 31), date(2026, 12, 1), today=TODAY)

    def test_rejects_a_span_one_day_too_long(self):
        start = date(2027, 1, 1)
        with pytest.raises(DateRangeError):
            check_date_range(start, start + timedelta(days=MAX_SPAN_DAYS + 1), today=TODAY)

    def test_rejects_an_end_past_the_booking_horizon(self):
        end = TODAY + timedelta(days=MAX_DAYS_AHEAD + 1)
        with pytest.raises(DateRangeError):
            check_date_range(end - timedelta(days=3), end, today=TODAY)

    def test_rejects_the_far_future(self):
        with pytest.raises(DateRangeError):
            check_date_range(date(9999, 11, 1), date(9999, 12, 31), today=TODAY)

    def test_horizon_covers_wa_nine_month_window(self):
        assert MAX_DAYS_AHEAD >= 9 * 31


class TestCheckSpecificRefusesBeforeFetching:
    async def test_no_provider_call_on_a_bad_range(self):
        engine = SearchEngine.__new__(SearchEngine)
        engine._registry = MagicMock()
        engine._check_campground = AsyncMock()
        with pytest.raises(DateRangeError):
            await engine.check_specific("232465", date(2027, 1, 1), date(2028, 1, 1))
        engine._check_campground.assert_not_called()


_FAR = "start_date=2027-01-01&end_date=9999-12-01"
_BACKWARDS = "start_date=2027-01-31&end_date=2027-01-01"


@pytest.mark.parametrize("params", [_FAR, _BACKWARDS])
class TestRoutesReturn422:
    def test_search(self, api_client: TestClient, params: str):
        resp = api_client.get(f"/api/search?{params}")
        assert resp.status_code == 422
        api_module._engine.search.assert_not_called()

    def test_search_stream(self, api_client: TestClient, params: str):
        resp = api_client.get(f"/api/search/stream?{params}")
        assert resp.status_code == 422
        api_module._engine.search_stream.assert_not_called()

    def test_check(self, api_client: TestClient, params: str):
        resp = api_client.get(f"/api/check/232465?{params}")
        assert resp.status_code == 422
        api_module._engine.check_specific.assert_not_called()
