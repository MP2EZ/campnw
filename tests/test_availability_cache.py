"""Availability cache correctness.

A cached payload is served only when the range it covers includes the
requested range: a narrow payload must never answer a wider request, and a
wider payload (the poll_all prefetch) does answer a narrower one.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from pnw_campsites.registry.models import BookingSystem, Campground, CampgroundAvailability
from pnw_campsites.search.engine import SearchEngine, SearchQuery

PAYLOAD_WIDE = '{"campsites": {"wide": true}}'
PAYLOAD_NARROW = '{"campsites": {"narrow": true}}'


class TestCacheCoversRequestedRange:
    def test_narrow_cache_does_not_satisfy_wider_request(self, watch_db):
        """The correctness bug: a 3-day payload must not answer a 30-day query."""
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_NARROW, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 3),
        )
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        assert got is None, (
            "a payload covering only Jun 1-3 was served for a Jun 1-30 "
            "request — the caller would see incomplete availability"
        )

    def test_wide_cache_satisfies_narrower_request(self, watch_db):
        """A superset is a legitimate hit — this is what makes the poll_all
        prefetch actually dedupe."""
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 8, 31),
        )
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 10), range_end=date(2026, 6, 12),
        )
        assert got == PAYLOAD_WIDE

    def test_exact_range_hits(self, watch_db):
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        assert got == PAYLOAD_WIDE

    def test_prefetch_across_months_is_reused(self, watch_db):
        """poll_all prefetches one wide range per facility under the *wide*
        start month. A watch starting in a later month must still hit it."""
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 9, 30),
        )
        # A July watch — different start month from the cached row's key.
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 7, 4), range_end=date(2026, 7, 6),
        )
        assert got == PAYLOAD_WIDE, (
            "the per-facility prefetch did not serve a watch in a later "
            "month, which is the case it exists to cover"
        )

    def test_partial_overlap_is_a_miss(self, watch_db):
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_NARROW, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 15),
        )
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 10), range_end=date(2026, 6, 25),
        )
        assert got is None

    def test_source_still_isolates_entries(self, watch_db):
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        assert watch_db.get_cached_availability(
            "232465", "wa_state",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        ) is None

    def test_campground_still_isolates_entries(self, watch_db):
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        assert watch_db.get_cached_availability(
            "999999", "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        ) is None

    def test_legacy_rows_without_a_range_are_not_served(self, watch_db):
        """Rows written before the migration have no recorded extent. We can't
        prove they cover anything, so they must miss rather than risk serving
        incomplete data. Self-heals on the next fetch."""
        watch_db._conn.execute(
            "INSERT OR REPLACE INTO availability_cache"
            " (campground_id, month, source, payload, cached_at)"
            " VALUES (?, ?, ?, ?, datetime('now'))",
            ("232465", "2026-06", "recgov", PAYLOAD_NARROW),
        )
        watch_db._conn.commit()
        got = watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 3),
        )
        assert got is None

    def test_expired_entries_still_miss(self, watch_db):
        watch_db.set_cached_availability(
            "232465", "2026-06", PAYLOAD_WIDE, "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        )
        # Age the row past the TTL.
        watch_db._conn.execute(
            "UPDATE availability_cache SET cached_at = datetime('now', '-1 day')"
        )
        watch_db._conn.commit()
        assert watch_db.get_cached_availability(
            "232465", "recgov",
            range_start=date(2026, 6, 1), range_end=date(2026, 6, 30),
        ) is None


class TestSearchUsesTheCache:
    """Discovery search shares the poller's availability cache."""

    @pytest.fixture
    def check(self, watch_db):
        """Returns (recgov mock, async fn that runs _check_campground for a range)."""
        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=CampgroundAvailability(facility_id="232465", campsites={})
        )
        engine = SearchEngine(registry=None, recgov_client=recgov, watch_db=watch_db)
        cg = Campground(
            facility_id="232465", name="Ohanapecosh",
            booking_system=BookingSystem.RECGOV, state="WA",
        )

        async def run(start: date, end: date) -> None:
            await engine._check_campground(
                cg, start, end, SearchQuery(start_date=start, end_date=end),
            )

        return recgov, run

    async def test_second_check_is_served_from_cache(self, check):
        recgov, run = check
        for _ in range(3):
            await run(date(2026, 6, 1), date(2026, 6, 3))

        assert recgov.get_availability_range.await_count == 1

    async def test_wider_request_is_not_served_by_a_narrow_cached_payload(self, check):
        recgov, run = check
        await run(date(2026, 6, 1), date(2026, 6, 3))
        await run(date(2026, 6, 1), date(2026, 6, 30))

        assert recgov.get_availability_range.await_count == 2
