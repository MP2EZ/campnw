"""Tests for cancellation stats and booking tips."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.analytics.patterns import (
    extract_booking_tips,
    get_availability_summary,
    refresh_all_tips,
)
from pnw_campsites.registry.models import BookingSystem
from tests.conftest import make_campground

TODAY = date(2026, 8, 1)
FIRST_SEEN = datetime(2026, 5, 1, 8)
LAST_SEEN = datetime(2026, 7, 31, 23)
NIGHTS = [date(2026, 6, 1) + timedelta(days=i) for i in range(61)]  # Jun-Jul


def _daily(db, cg, site, night, status, source="recgov", first=FIRST_SEEN):
    db._conn.execute(
        "INSERT OR REPLACE INTO availability_daily"
        " (campground_id, site_id, date, status, source,"
        "  first_seen, last_seen, observation_count)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (cg, site, night.isoformat(), status, source,
         first.isoformat(), LAST_SEEN.isoformat()),
    )


def _transition(db, cg, site, night, old, new, at: datetime):
    db._conn.execute(
        "INSERT INTO status_transitions"
        " (campground_id, site_id, date, old_status, new_status, source,"
        "  observed_at) VALUES (?, ?, ?, ?, ?, 'recgov', ?)",
        (cg, site, night.isoformat(), old, new, at.isoformat()),
    )


def _seed_season(db, cg="CG1", sites=20, source="recgov", first=FIRST_SEEN):
    """Every site booked every night; site s0 cancels Mon-Thu nights.

    Each cancellation comes 5 days out and is rebooked 2 hours later.
    """
    for night in NIGHTS:
        for s in range(sites):
            _daily(db, cg, f"s{s}", night, "Reserved", source, first)
            _transition(db, cg, f"s{s}", night, "", "Reserved", first)
        if night.weekday() <= 3:
            at = datetime.combine(night - timedelta(days=5), datetime.min.time())
            _transition(db, cg, "s0", night, "Reserved", "Available", at)
            _transition(db, cg, "s0", night, "Available", "Reserved",
                        at + timedelta(hours=2))
    db._conn.commit()


def _mock_client(text: str | None = None, error: Exception | None = None):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response, side_effect=error)
    return client


class TestAvailabilitySummary:
    def test_none_when_checked_for_under_30_days(self, watch_db):
        _seed_season(watch_db, first=LAST_SEEN - timedelta(days=10))
        assert get_availability_summary(watch_db, "CG1", TODAY) is None

    def test_none_when_history_is_stale(self, watch_db):
        _seed_season(watch_db)
        assert get_availability_summary(watch_db, "CG1", date(2026, 10, 1)) is None

    def test_none_when_too_few_booked_nights(self, watch_db):
        _seed_season(watch_db, sites=1)
        assert get_availability_summary(watch_db, "CG1", TODAY) is None

    def test_none_for_unknown_campground(self, watch_db):
        assert get_availability_summary(watch_db, "nope", TODAY) is None

    def test_cancellation_timing_and_weekday_rates(self, watch_db):
        _seed_season(watch_db)
        s = get_availability_summary(watch_db, "CG1", TODAY)
        assert s["months"] == "June to July 2026"
        assert s["booked_site_nights"] == 20 * 61
        assert s["pct_of_cancellations_by_days_before_arrival"]["3-7"] == 100.0
        rates = s["pct_of_booked_site_nights_that_reopened_by_night_of_week"]
        assert rates["Monday"] == 5.0  # 1 of 20 sites
        assert rates["Friday"] == rates["Saturday"] == 0.0
        assert s["median_time_a_reopened_site_stayed_open"] == "2 hours"

    def test_statuses_that_are_not_bookings_are_excluded(self, watch_db):
        _seed_season(watch_db)
        night = NIGHTS[0]
        for site, status in [("x1", "NYR"), ("x2", "Closed"), ("x3", "Open"),
                             ("x4", "Not Reservable")]:
            _daily(watch_db, "CG1", site, night, status)
        s = get_availability_summary(watch_db, "CG1", TODAY)
        assert s["booked_site_nights"] == 20 * 61
        assert s["excluded_site_nights_not_booked_online"] == {
            "not_yet_released": 1, "closed": 1,
            "first_come_first_served": 1, "not_reservable": 1,
        }

    def test_cart_hold_is_not_a_cancellation(self, watch_db):
        _seed_season(watch_db)
        before = get_availability_summary(watch_db, "CG1", TODAY)["cancellations"]
        night, at = NIGHTS[4], datetime(2026, 6, 1, 9)
        _transition(watch_db, "CG1", "hold", night, "", "Available", FIRST_SEEN)
        _transition(watch_db, "CG1", "hold", night, "Available", "Reserved", at)
        _transition(watch_db, "CG1", "hold", night, "Reserved", "Available",
                    at + timedelta(minutes=15))
        s = get_availability_summary(watch_db, "CG1", TODAY)
        assert s["cancellations"] == before

    def test_nights_after_last_check_are_left_out(self, watch_db):
        _seed_season(watch_db)
        before = get_availability_summary(watch_db, "CG1", TODAY)
        late = date(2026, 8, 20)
        _transition(watch_db, "CG1", "s1", late, "", "Reserved", FIRST_SEEN)
        _transition(watch_db, "CG1", "s1", late, "Reserved", "Available",
                    datetime(2026, 7, 30))
        after = get_availability_summary(watch_db, "CG1", TODAY)
        assert after["cancellations"] == before["cancellations"]
        assert after["booked_site_nights"] == before["booked_site_nights"]

    def test_reopened_night_that_ends_unreservable_stays_under_100(self, watch_db):
        _seed_season(watch_db)
        for night in NIGHTS:
            if night.weekday() == 0:
                _daily(watch_db, "CG1", "s0", night, "Not Reservable")
        s = get_availability_summary(watch_db, "CG1", TODAY)
        rates = s["pct_of_booked_site_nights_that_reopened_by_night_of_week"]
        assert all(r <= 100 for r in rates.values())


class TestExtractBookingTips:
    async def test_no_tips_without_api_key(self, watch_db):
        _seed_season(watch_db)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            assert await extract_booking_tips(watch_db, "CG1", today=TODAY) == []

    async def test_no_tips_without_enough_history(self, watch_db):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}):
            assert await extract_booking_tips(watch_db, "CG1", today=TODAY) == []

    async def test_keeps_only_tips_the_numbers_back(self, watch_db):
        _seed_season(watch_db)
        good = ("In June to July 2026, 100.0% of cancellations came 3 to 7 days"
                " before arrival.")
        llm = json.dumps([
            good,
            "In June to July 2026, sites sell out fast, book immediately.",
            "In June to July 2026, 42% of Monday nights reopened.",
            "In June to July 2026, Mondays saw the most reopenings.",
            123,
        ])
        client = _mock_client(f"```json\n{llm}\n```")
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}),
            patch("pnw_campsites.posthog_client.get_anthropic_client",
                  return_value=client),
        ):
            tips = await extract_booking_tips(watch_db, "CG1", "Lake", TODAY)
        assert tips == [good]
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "June to July 2026" in prompt
        assert "not bookings" in prompt

    @pytest.mark.parametrize("text,error", [
        ("not json", None), ('{"tip": "x"}', None), (None, TimeoutError()),
    ])
    async def test_bad_llm_reply_gives_no_tips(self, watch_db, text, error):
        _seed_season(watch_db)
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}),
            patch("pnw_campsites.posthog_client.get_anthropic_client",
                  return_value=_mock_client(text, error)),
        ):
            assert await extract_booking_tips(watch_db, "CG1", today=TODAY) == []


class TestRefreshAllTips:
    TIP = "In June to July 2026, 5.0% of Monday nights reopened."

    async def _refresh(self, watch_db, registry, client, today=TODAY):
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}),
            patch("pnw_campsites.posthog_client.get_anthropic_client",
                  return_value=client),
        ):
            return await refresh_all_tips(watch_db, registry, today)

    async def test_writes_tips_for_wa_state_campground(self, watch_db, registry):
        cg = registry.upsert(make_campground(
            facility_id="-2147483624", booking_system=BookingSystem.WA_STATE,
        ))
        _seed_season(watch_db, cg="-2147483624", source="wa_state")
        client = _mock_client(json.dumps([self.TIP]))
        assert await self._refresh(watch_db, registry, client) == 1
        assert json.loads(registry.get_by_id(cg.id).booking_tips) == [self.TIP]

    async def test_clears_tips_once_history_is_stale(self, watch_db, registry):
        cg = registry.upsert(make_campground(facility_id="CG1"))
        registry.update_booking_tips(cg.id, json.dumps(["old"]))
        _seed_season(watch_db)
        client = _mock_client(json.dumps([self.TIP]))
        assert await self._refresh(watch_db, registry, client, date(2026, 11, 1)) == 0
        assert registry.get_by_id(cg.id).booking_tips == ""
        client.messages.create.assert_not_called()

    async def test_failed_llm_call_keeps_previous_tips(self, watch_db, registry):
        cg = registry.upsert(make_campground(facility_id="CG1"))
        registry.update_booking_tips(cg.id, json.dumps(["old"]))
        _seed_season(watch_db)
        client = _mock_client(error=TimeoutError())
        assert await self._refresh(watch_db, registry, client) == 0
        assert json.loads(registry.get_by_id(cg.id).booking_tips) == ["old"]
