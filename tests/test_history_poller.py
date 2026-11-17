"""History poller: availability history that keeps growing without watches.

Prod history stopped on 2026-07-31. Every recorded campground came from a seed
watch starting 2026-04-15. Rec.gov rejects months more than about three back
(400, "Please select a date within the next two years."), so from Aug 1 each
poll's April request failed the whole fetch and nothing was written.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import pnw_campsites.api as api_module
from pnw_campsites import health
from pnw_campsites.monitor import history
from pnw_campsites.monitor.history import history_months, record_history
from pnw_campsites.providers.errors import RateLimitedError
from tests.conftest import make_campground_availability, make_campsite_availability

TODAY = date(2026, 11, 16)


def _month_payload(fid: str, month: date):
    days = {
        f"{month.replace(day=d).isoformat()}T00:00:00.000Z": "Reserved"
        for d in (1, 15, 28)
    }
    site = make_campsite_availability(campsite_id="s1", dates_status=days)
    return make_campground_availability(facility_id=fid, campsites={"s1": site})


def _recgov(side_effect=None):
    recgov = AsyncMock()
    recgov.get_availability.side_effect = side_effect or _month_payload
    return recgov


def _rows(watch_db, table: str) -> list:
    return watch_db._conn.execute(f"SELECT * FROM {table}").fetchall()


# --- window -----------------------------------------------------------------


def test_months_run_from_this_month_through_the_lookahead():
    assert history_months(TODAY) == [
        date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1),
    ]


def test_months_never_include_a_past_month():
    """A past month 400s on rec.gov once it is about three months old."""
    assert history_months(date(2026, 12, 31))[0] == date(2026, 12, 1)


# --- job --------------------------------------------------------------------


async def test_records_every_facility_and_month(watch_db):
    recgov = _recgov()
    written = await record_history(recgov, watch_db, today=TODAY, facilities=("A", "B"))

    assert recgov.get_availability.await_count == 2 * len(history_months(TODAY))
    campgrounds = {r["campground_id"] for r in _rows(watch_db, "availability_daily")}
    assert campgrounds == {"A", "B"}
    assert written == len(_rows(watch_db, "availability_daily"))


async def test_past_nights_are_not_recorded(watch_db):
    await record_history(_recgov(), watch_db, today=TODAY, facilities=("A",))

    dates = {r["date"] for r in _rows(watch_db, "availability_daily")}
    assert "2026-11-01" not in dates and "2026-11-15" not in dates
    assert "2026-11-28" in dates


async def test_a_failed_month_costs_only_that_month(watch_db):
    def fetch(fid, month):
        if month == date(2026, 12, 1):
            request = httpx.Request("GET", "https://www.recreation.gov")
            raise httpx.HTTPStatusError(
                "400", request=request, response=httpx.Response(400, request=request),
            )
        return _month_payload(fid, month)

    await record_history(_recgov(fetch), watch_db, today=TODAY, facilities=("A",))

    months = {r["date"][:7] for r in _rows(watch_db, "availability_daily")}
    assert months == {"2026-11", "2027-01", "2027-02"}


async def test_rate_limit_stops_the_cycle(watch_db):
    recgov = _recgov(RateLimitedError("429"))
    await record_history(recgov, watch_db, today=TODAY, facilities=("A", "B"))

    assert recgov.get_availability.await_count == 1
    assert _rows(watch_db, "availability_daily") == []


async def test_job_records_the_configured_facilities(watch_db, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_FACILITIES", ("A",))
    with (
        patch.object(api_module, "_watch_db", watch_db),
        patch.object(api_module, "_recgov", _recgov()),
    ):
        await api_module._record_history()

    assert {r["campground_id"] for r in _rows(watch_db, "availability_daily")} == {"A"}


async def test_job_without_recgov_is_a_noop(watch_db):
    with (
        patch.object(api_module, "_watch_db", watch_db),
        patch.object(api_module, "_recgov", None),
    ):
        await api_module._record_history()


def test_history_facilities_are_unique():
    assert len(set(history.HISTORY_FACILITIES)) == len(history.HISTORY_FACILITIES)


# --- retention --------------------------------------------------------------


def test_prune_drops_nights_before_the_cutoff(watch_db):
    watch_db.record_availability_history(
        "A", [("s1", "2025-01-10", "Reserved"), ("s1", "2026-06-01", "Reserved")],
    )

    removed = watch_db.prune_availability_history(before=date(2025, 6, 1))

    assert removed == 2  # one daily row, one transition
    assert [r["date"] for r in _rows(watch_db, "availability_daily")] == ["2026-06-01"]
    assert [r["date"] for r in _rows(watch_db, "status_transitions")] == ["2026-06-01"]


async def test_prune_job_keeps_thirteen_months(watch_db):
    with (
        patch.object(api_module, "_watch_db", watch_db),
        patch.object(api_module, "pacific_today", lambda: TODAY),
        patch.object(watch_db, "prune_availability_history", return_value=0) as prune,
    ):
        await api_module._prune_history()

    prune.assert_called_once_with(before=date(2025, 10, 12))


# --- doctor -----------------------------------------------------------------


def _history_db(tmp_path, last_seen: datetime):
    from pnw_campsites.monitor.db import WatchDB

    path = tmp_path / "watches.db"
    db = WatchDB(path)
    db.record_availability_history(health.PROBE_FACILITY_ID, [("s1", "2027-06-01", "Reserved")])
    db._conn.execute("UPDATE availability_daily SET last_seen=?", (last_seen.isoformat(),))
    db._conn.commit()
    db.close()
    return path


async def test_doctor_passes_when_history_is_fresh(tmp_path, monkeypatch):
    path = _history_db(tmp_path, datetime.now() - timedelta(minutes=20))
    monkeypatch.setattr("pnw_campsites.monitor.db.DEFAULT_DB_PATH", path)
    assert "last recorded" in await health._check_availability_history()


async def test_doctor_fails_when_history_is_stale(tmp_path, monkeypatch):
    path = _history_db(tmp_path, datetime.now() - timedelta(days=2))
    monkeypatch.setattr("pnw_campsites.monitor.db.DEFAULT_DB_PATH", path)
    with pytest.raises(RuntimeError, match="not grown"):
        await health._check_availability_history()


async def test_doctor_skips_where_the_poller_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_POLLER", "0")
    with pytest.raises(health.SkipCheck):
        await health._check_availability_history()
