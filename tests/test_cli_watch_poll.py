"""CLI `watch poll` (local/manual polling)."""

from __future__ import annotations

import argparse
import asyncio
from unittest.mock import AsyncMock, MagicMock

from pnw_campsites import __main__ as cli
from pnw_campsites.monitor.db import Watch, WatchDB
from tests.conftest import make_campground_availability, make_campsite_availability


def test_watch_poll_polls_and_reports_new_sites(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "w.db"
    with WatchDB(db_path) as db:
        db.add_watch(Watch(facility_id="232465", name="Camp",
                           start_date="2027-06-04", end_date="2027-06-05"))

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get_availability_range.return_value = make_campground_availability(
        "232465", {"A1": make_campsite_availability(
            campsite_id="A1", site="A1", dates_status={"2027-06-04T00:00:00.000Z": "Available"},
        )},
    )
    monkeypatch.setenv("RIDB_API_KEY", "test")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "RecGovClient", lambda **_: client)
    monkeypatch.setattr(cli, "WatchDB", lambda: WatchDB(db_path))
    monkeypatch.setattr(cli, "CampgroundRegistry", lambda: MagicMock(booking_systems_for=lambda _: []))

    asyncio.run(cli.cmd_watch_poll(argparse.Namespace()))

    out = capsys.readouterr().out
    assert "[ERROR]" not in out
    assert "Polled 1 watch(es). 1 new site(s) found." in out
