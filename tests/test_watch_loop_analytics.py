"""The watch -> notify loop must be observable (audit ANLT-03).

Watch fires -> notification lands -> user books is the product's entire reason
to exist, and none of it reached analytics: db.log_notification wrote a row
nothing analysed. You could not answer what fraction of watches ever fire, the
median time to first alert, or whether an alert ever produced a booking.

These exercise the real dispatch loop in api._poll_tranche with poll_all
stubbed, so a regression in the loop's structure (not just in the helper) is
caught.
"""

from __future__ import annotations

import pytest

from pnw_campsites import api as api_module
from pnw_campsites.monitor.db import Watch
from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult


def _result(
    *, user_id: int | None = 7, changes: int = 2, channel: str = "ntfy",
) -> PollResult:
    watch = Watch(
        id=42, facility_id="232465", user_id=user_id,
        booking_system="recgov", notification_channel=channel,
        notify_topic="topic", name="Ohanapecosh",
    )
    r = PollResult(watch=watch)
    r.current_available = changes
    for i in range(changes):
        r.changes.append(
            AvailabilityChange(
                watch=watch, site_id=str(i), site_name=f"A{i}", loop="",
                campsite_type="tent", new_dates=["2026-06-05"], max_people=4,
            )
        )
    return r


class _StubDB:
    def __init__(self):
        self.logged: list[tuple] = []

    def log_notification(self, *args, **kwargs):
        self.logged.append((args, kwargs))


@pytest.fixture
def captured(monkeypatch):
    """Collect capture_event calls made by the dispatch loop."""
    events: list[dict] = []
    monkeypatch.setattr(
        api_module, "capture_event",
        lambda **kw: events.append(kw),
    )
    monkeypatch.setattr(api_module, "_watch_db", _StubDB())
    monkeypatch.setattr(api_module, "_poll_state", {})
    return events


async def _run(results, monkeypatch, *, notify=None):
    """Drive the real dispatch loop with poll_all and the notifier stubbed.

    _poll_tranche imports poll_all and notify_ntfy *inside* the function, so
    the bindings to patch live in their defining modules — patching
    pnw_campsites.api would create attributes the loop never reads.
    """
    from pnw_campsites.monitor import notify as notify_mod
    from pnw_campsites.monitor import watcher as watcher_mod

    async def fake_poll_all(*a, **k):
        return results

    async def default_notify(*a, **k):
        return None

    monkeypatch.setattr(watcher_mod, "poll_all", fake_poll_all)
    monkeypatch.setattr(notify_mod, "notify_ntfy", notify or default_notify)
    await api_module._poll_tranche()


class TestWatchTriggered:
    @pytest.mark.asyncio
    async def test_a_firing_watch_emits_watch_triggered(self, captured, monkeypatch):
        await _run([_result(changes=3)], monkeypatch)

        triggered = [e for e in captured if e["event"] == "watch_triggered"]
        assert len(triggered) == 1, (
            "a watch that freed sites emitted no watch_triggered — the "
            "fraction of watches that ever fire stays uncomputable"
        )
        assert triggered[0]["distinct_id"] == "7"
        assert triggered[0]["properties"]["sites_freed"] == 3
        assert triggered[0]["properties"]["facility_id"] == "232465"

    @pytest.mark.asyncio
    async def test_a_watch_with_no_changes_emits_nothing(self, captured, monkeypatch):
        await _run([_result(changes=0)], monkeypatch)
        assert [e for e in captured if e["event"] == "watch_triggered"] == []

    @pytest.mark.asyncio
    async def test_anonymous_watches_still_get_a_stable_distinct_id(
        self, captured, monkeypatch,
    ):
        """Anonymous watches have no user_id. Passing None would drop the event
        on the floor, so they key on the watch itself."""
        await _run([_result(user_id=None)], monkeypatch)

        triggered = [e for e in captured if e["event"] == "watch_triggered"]
        assert triggered and triggered[0]["distinct_id"] == "watch:42"


class TestNotificationDispatch:
    @pytest.mark.asyncio
    async def test_successful_send_emits_notification_sent(
        self, captured, monkeypatch,
    ):
        await _run([_result()], monkeypatch)

        sent = [e for e in captured if e["event"] == "notification_sent"]
        assert len(sent) == 1
        assert sent[0]["properties"]["channel"] == "ntfy"
        assert sent[0]["properties"]["sites_in_message"] == 2

    @pytest.mark.asyncio
    async def test_a_failed_send_emits_notification_failed(
        self, captured, monkeypatch,
    ):
        """A watch that fires but whose notification never lands is a different
        failure from one that never fires, and the two must be separable."""
        async def boom(*a, **k):
            raise RuntimeError("ntfy down")

        await _run([_result()], monkeypatch, notify=boom)

        assert [e["event"] for e in captured if e["event"] == "notification_failed"]
        assert not [e for e in captured if e["event"] == "notification_sent"]
