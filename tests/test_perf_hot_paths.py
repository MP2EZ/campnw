"""Regression tests for the audited hot paths (see .audit-report.md, batch 2a).

Each test here pins a property that was measured to be wrong, not merely slow:
a query that reads more rows than it needs, an aggregation done in Python that
SQL can do, and a fan-out whose own cap was silently discarded. They are
written so they fail on the pre-fix code for the *reason stated*, not
incidentally.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pnw_campsites.registry.models import BookingSystem, Campground


def make_campground(**overrides) -> Campground:
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


# ---------------------------------------------------------------------------
# PERF-02 — record_availability_history must not read the whole partition
# ---------------------------------------------------------------------------


class TestAvailabilityHistoryReadIsBounded:
    """The transition-detection read must be scoped to the dates being written.

    Measured on a copy of the production watches.db, facility 232464: the
    unbounded read materialized all 18,705 accumulated rows to diff a single
    month's 4,350; bounding it plus the (campground_id, date) index took the
    read from ~20ms to ~4ms. The absolute numbers are machine-dependent — the
    structural point is that the old read is O(total history) and the new one
    is O(polled window), so the gap widens permanently.
    """

    def _seed(self, watch_db, campground_id: str, dates: list[str], status: str):
        watch_db.record_availability_history(
            campground_id,
            [("site1", d, status) for d in dates],
        )

    def test_reads_only_rows_in_the_written_date_range(self, watch_db):
        old = [f"2026-01-{d:02d}" for d in range(1, 29)]
        new = [f"2026-09-{d:02d}" for d in range(1, 15)]
        self._seed(watch_db, "232465", old, "Available")
        self._seed(watch_db, "232465", new, "Available")

        # sqlite3.Connection.execute is read-only, so count rows through a
        # forwarding proxy rather than by patching the method.
        counter = {"rows": 0}
        real_conn = watch_db._conn

        class _CountingConn:
            def __getattr__(self, name):
                return getattr(real_conn, name)

            def execute(self, sql, params=()):
                cursor = real_conn.execute(sql, params)
                if "FROM availability_daily" in sql and "SELECT site_id" in sql:
                    rows = cursor.fetchall()
                    counter["rows"] += len(rows)
                    return _Replay(rows)
                return cursor

        class _Replay:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        watch_db._conn = _CountingConn()
        try:
            # Re-record only the September window.
            self._seed(watch_db, "232465", new, "Reserved")
        finally:
            watch_db._conn = real_conn

        # 14 September rows are relevant; the 28 January rows are not.
        assert counter["rows"] == len(new), (
            f"read {counter['rows']} rows to diff {len(new)}; the January "
            "partition is being loaded needlessly"
        )

    def test_transitions_still_detected_within_the_window(self, watch_db):
        """Narrowing the read must not lose transition detection."""
        dates = ["2026-09-01", "2026-09-02"]
        self._seed(watch_db, "232465", dates, "Reserved")
        self._seed(watch_db, "232465", dates, "Available")

        rows = watch_db._conn.execute(
            "SELECT old_status, new_status FROM status_transitions"
            " WHERE campground_id=? AND date=? ORDER BY id",
            ("232465", "2026-09-01"),
        ).fetchall()
        # First write: "" -> Reserved. Second: Reserved -> Available.
        assert [tuple(r) for r in rows] == [
            ("", "Reserved"),
            ("Reserved", "Available"),
        ]

    def test_no_transition_logged_when_status_unchanged(self, watch_db):
        dates = ["2026-09-01"]
        self._seed(watch_db, "232465", dates, "Available")
        before = watch_db._conn.execute(
            "SELECT COUNT(*) FROM status_transitions"
        ).fetchone()[0]
        self._seed(watch_db, "232465", dates, "Available")
        after = watch_db._conn.execute(
            "SELECT COUNT(*) FROM status_transitions"
        ).fetchone()[0]
        assert after == before

    def test_other_campgrounds_are_not_confused(self, watch_db):
        """Scoping by date must not accidentally widen across campgrounds."""
        self._seed(watch_db, "232465", ["2026-09-01"], "Available")
        self._seed(watch_db, "999999", ["2026-09-01"], "Reserved")
        # Re-record 232465 with the same status — no transition expected even
        # though a different campground has a different status on that date.
        self._seed(watch_db, "232465", ["2026-09-01"], "Available")
        rows = watch_db._conn.execute(
            "SELECT COUNT(*) FROM status_transitions WHERE campground_id=?",
            ("232465",),
        ).fetchone()[0]
        assert rows == 1  # only the initial "" -> Available


# ---------------------------------------------------------------------------
# PERF-19 — get_all_tags aggregated in SQL, same result
# ---------------------------------------------------------------------------


class TestGetAllTags:
    """Rewriting the Python Counter loop as a json_each aggregate must be a
    no-op behaviourally. Measured ~2.6x faster on the 1,368-row registry, with
    byte-identical output."""

    def test_counts_and_ordering_match_expected(self, registry):
        registry.upsert(make_campground(facility_id="1", tags=["lakeside", "pets"]))
        registry.upsert(make_campground(facility_id="2", tags=["lakeside"]))
        registry.upsert(make_campground(facility_id="3", tags=["pets", "quiet"]))

        # Sorted by count desc, then tag name asc.
        assert registry.get_all_tags() == [
            ("lakeside", 2),
            ("pets", 2),
            ("quiet", 1),
        ]

    def test_excludes_disabled_campgrounds(self, registry):
        registry.upsert(make_campground(facility_id="1", tags=["lakeside"]))
        registry.upsert(
            make_campground(facility_id="2", tags=["lakeside"], enabled=False)
        )
        assert registry.get_all_tags() == [("lakeside", 1)]

    def test_handles_empty_and_missing_tags(self, registry):
        registry.upsert(make_campground(facility_id="1", tags=[]))
        registry.upsert(make_campground(facility_id="2", tags=["lakeside"]))
        assert registry.get_all_tags() == [("lakeside", 1)]

    def test_empty_registry_returns_empty_list(self, registry):
        assert registry.get_all_tags() == []


# ---------------------------------------------------------------------------
# PERF-03 — narrow projection for the sitemap
# ---------------------------------------------------------------------------


class TestListSlugs:
    """/sitemap.xml needs (state, slug) and nothing else. Hydrating 1,368 full
    pydantic models to reach two columns measured ~26x slower than the narrow
    query on the production registry."""

    def test_returns_state_and_slug_only(self, registry):
        registry.upsert(
            make_campground(facility_id="1", name="Ohanapecosh", state="WA")
        )
        rows = registry.list_slugs()
        assert len(rows) == 1
        state, slug = rows[0]
        assert state == "WA"
        assert slug  # populated by the upsert's slug derivation

    def test_excludes_disabled(self, registry):
        registry.upsert(make_campground(facility_id="1", state="WA"))
        registry.upsert(make_campground(facility_id="2", state="OR", enabled=False))
        assert [s for s, _ in registry.list_slugs()] == ["WA"]

    def test_matches_list_all_membership(self, registry):
        """The narrow query must select the same rows as the hydrating one."""
        for i in range(5):
            registry.upsert(
                make_campground(facility_id=str(i), name=f"CG {i}", state="WA")
            )
        registry.upsert(
            make_campground(facility_id="9", name="Off", enabled=False)
        )
        assert sorted(registry.list_slugs()) == sorted(
            (cg.state, cg.slug) for cg in registry.list_all()
        )


# ---------------------------------------------------------------------------
# PERF-04 — zero-result date probes must honour their own campground cap
# ---------------------------------------------------------------------------


class TestDateSuggestionProbeCap:
    """`_suggest_alternative_dates` builds probe queries with
    max_campgrounds=5, but passed a _PreparedSearch carrying the *full*
    campground list; search() does `prep = _prep or await self._prepare_search()`
    so the cap was silently discarded. Three gathered probes then re-checked
    every campground — up to 180 extra provider fetches on exactly the searches
    that already returned nothing."""

    @pytest.mark.asyncio
    async def test_probes_are_capped_to_their_query_limit(self, monkeypatch):
        from pnw_campsites.search import engine as engine_mod

        registry_rows = [
            make_campground(facility_id=str(i), name=f"CG {i}") for i in range(60)
        ]

        eng = engine_mod.SearchEngine.__new__(engine_mod.SearchEngine)

        prepared = engine_mod._PreparedSearch(
            campgrounds=registry_rows,
            drive_times={},
            registry_count=len(registry_rows),
            distance_filtered=False,
            start_month=date(2026, 6, 1),
            end_month=date(2026, 6, 30),
            from_coords=None,
        )

        async def fake_prepare(_query):
            return prepared

        checked_per_probe: list[int] = []

        async def fake_search(query, *, _skip_diagnosis=False, _prep=None):
            checked = len(_prep.campgrounds) if _prep else 0
            checked_per_probe.append(checked)
            return engine_mod.SearchResults(
                query=query,
                results=[],
                campgrounds_checked=checked,
                campgrounds_with_availability=0,
            )

        monkeypatch.setattr(eng, "_prepare_search", fake_prepare)
        monkeypatch.setattr(eng, "search", fake_search)

        query = engine_mod.SearchQuery(
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=33),
            state="WA",
        )

        await eng._suggest_alternative_dates(query)

        assert checked_per_probe, "no probes ran"
        assert all(n <= 5 for n in checked_per_probe), (
            f"probe checked {max(checked_per_probe)} campgrounds; the probe "
            "query's max_campgrounds=5 was discarded"
        )
