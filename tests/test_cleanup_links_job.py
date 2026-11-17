"""The daily job that purges expired share links."""

from __future__ import annotations

from unittest.mock import patch

import pnw_campsites.api as api_module
from pnw_campsites.monitor.db import User


async def test_cleanup_job_purges_only_expired_links(watch_db):
    user = watch_db.create_user(User(email="a@example.com"))
    trip = watch_db.create_trip(user.id, "Trip")
    expired = watch_db.create_shared_link(user.id, trip_id=trip.id, expires_days=-1)
    live = watch_db.create_shared_link(user.id, trip_id=trip.id, expires_days=30)

    with patch.object(api_module, "_watch_db", watch_db):
        await api_module._cleanup_expired_links()

    assert watch_db.get_shared_link(expired.uuid) is None
    assert watch_db.get_shared_link(live.uuid) is not None


async def test_cleanup_job_without_db_is_a_noop():
    with patch.object(api_module, "_watch_db", None):
        await api_module._cleanup_expired_links()
