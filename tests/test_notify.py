"""Tests for notification formatters and dispatch (notify.py)."""

from __future__ import annotations

import httpx
import respx

from pnw_campsites.monitor.db import Watch
from pnw_campsites.monitor.notify import (
    format_change,
    format_poll_result,
    notify_ntfy,
    notify_pushover,
    notify_web_push,
)
from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult


def _watch(**kw) -> Watch:
    kw = {
        "id": 1,
        "facility_id": "232465",
        "name": "Test Camp",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        **kw,
    }
    return Watch(**kw)


def _change(watch: Watch, **kw) -> AvailabilityChange:
    kw = {
        "site_id": "123456",
        "site_name": "A001",
        "loop": "Loop A",
        "campsite_type": "STANDARD",
        "new_dates": ["2026-06-01"],
        "max_people": 6,
        **kw,
    }
    return AvailabilityChange(watch=watch, **kw)


def _result(watch: Watch | None = None, *changes: AvailabilityChange) -> PollResult:
    return PollResult(watch=watch or _watch(), changes=list(changes))


def _body(request: httpx.Request) -> str:
    return request.content.decode()


class TestFormatChange:
    """Tests for format_change formatter."""

    def test_format_change_basic_structure(self):
        """format_change returns human-readable message with site and dates."""
        change = _change(_watch(), campsite_type="STANDARD NONELECTRIC")

        formatted = format_change(change)

        assert "Site A001" in formatted
        assert "Loop A" in formatted
        assert "max 6p" in formatted
        assert "Mon Jun 01" in formatted  # June 1, 2026 is Monday

    def test_format_change_multiple_dates(self):
        """format_change includes first 5 dates, shows count for more."""
        change = _change(_watch(), new_dates=[f"2026-06-0{d}" for d in range(1, 8)])

        formatted = format_change(change)

        # June 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun
        assert "Mon Jun 01" in formatted
        assert "Tue Jun 02" in formatted
        assert "Wed Jun 03" in formatted
        assert "Thu Jun 04" in formatted
        assert "Fri Jun 05" in formatted
        assert "+2 more" in formatted
        assert "Jun 06" not in formatted  # Truncated
        assert "Jun 07" not in formatted  # Truncated

    def test_format_change_single_date(self):
        """format_change with single date shows just that date."""
        change = _change(
            _watch(), site_name="Site X", loop="Loop B", campsite_type="ELECTRIC",
            new_dates=["2026-06-15"], max_people=4,
        )

        formatted = format_change(change)

        assert "Site X" in formatted
        assert "Loop B" in formatted
        assert "max 4p" in formatted
        assert "Mon Jun 15" in formatted
        assert "+0 more" not in formatted

    def test_format_change_date_formatting(self):
        """format_change dates are formatted as 'Day Mon DD'."""
        change = _change(_watch(start_date="2026-12-01", end_date="2026-12-31"), new_dates=["2026-12-25"])

        assert "Fri Dec 25" in format_change(change)


class TestFormatPollResult:
    """Tests for format_poll_result formatter."""

    def test_format_poll_result_single_change(self):
        """format_poll_result includes watch name, change count, and booking URL."""
        watch = _watch(name="Ohanapecosh Campground")
        result = _result(watch, _change(watch, campsite_type="STANDARD NONELECTRIC"))

        formatted = format_poll_result(result)

        assert "1 site open at Ohanapecosh Campground" in formatted
        assert "Site A001" in formatted
        assert "https://www.recreation.gov/camping/campgrounds/232465" in formatted
        assert "startDate=2026-06-01" in formatted

    def test_format_poll_result_multiple_changes(self):
        """format_poll_result shows up to 10 changes, then summary."""
        watch = _watch()
        changes = [_change(watch, site_id=f"site{i}", site_name=f"Site {i}") for i in range(15)]

        formatted = format_poll_result(_result(watch, *changes))

        assert "15 sites open at" in formatted
        assert "Site 0" in formatted
        assert "Site 9" in formatted
        assert "... and 5 more sites" in formatted
        assert "Site 10" not in formatted  # Beyond first 10

    def test_format_poll_result_zero_changes(self):
        """format_poll_result with zero changes still formats."""
        formatted = format_poll_result(_result())

        assert "0 sites open at Test Camp" in formatted
        assert "https://www.recreation.gov" in formatted

    def test_format_poll_result_includes_booking_url_with_date(self):
        """format_poll_result booking URL includes start_date param."""
        formatted = format_poll_result(
            _result(_watch(facility_id="999", start_date="2026-08-15", end_date="2026-08-31"))
        )

        assert "https://www.recreation.gov/camping/campgrounds/999" in formatted
        assert "startDate=2026-08-15" in formatted

    def test_format_poll_result_multi_line(self):
        """format_poll_result output is multi-line with proper structure."""
        watch = _watch()

        lines = format_poll_result(_result(watch, _change(watch))).split("\n")

        # Header, blank, site, blank, URL
        assert len(lines) >= 4
        assert "open at Test Camp" in lines[0]
        assert "Book:" in lines[-1]


class TestNotifyNtfy:
    """Tests for notify_ntfy dispatch function."""

    async def test_notify_ntfy_posts_to_correct_endpoint(self):
        """notify_ntfy POSTs to ntfy.sh with topic."""
        watch = _watch()

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(return_value=httpx.Response(200))

            await notify_ntfy("test-topic", _result(watch, _change(watch)))

            assert respx_mock.calls.called
            request = respx_mock.calls[0].request
            assert request.method == "POST"
            assert "test-topic" in request.url.path

    async def test_notify_ntfy_includes_headers(self):
        """notify_ntfy includes Title, Tags, Click, Priority headers."""
        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(return_value=httpx.Response(200))

            await notify_ntfy("test-topic", _result(_watch(name="My Campground")))

            request = respx_mock.calls[0].request
            assert request.headers["Title"] == "Campsite Alert: My Campground"
            assert request.headers["Tags"] == "tent,camping"
            assert "recreation.gov" in request.headers["Click"]
            assert request.headers["Priority"] == "high"

    async def test_notify_ntfy_custom_server(self):
        """notify_ntfy respects custom ntfy server parameter."""
        with respx.mock(base_url="https://ntfy.myserver.com") as respx_mock:
            respx_mock.post("/mytopic").mock(return_value=httpx.Response(200))

            await notify_ntfy("mytopic", _result(), server="https://ntfy.myserver.com")

            assert "ntfy.myserver.com" in str(respx_mock.calls[0].request.url)

    async def test_notify_ntfy_body_contains_message(self):
        """notify_ntfy POST body contains formatted message."""
        watch = _watch()

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(return_value=httpx.Response(200))

            await notify_ntfy("test-topic", _result(watch, _change(watch)))

            body = _body(respx_mock.calls[0].request)
            assert "open at Test Camp" in body
            assert "Site A001" in body

    async def test_notify_ntfy_handles_multiple_changes(self):
        """notify_ntfy includes all changes in message."""
        watch = _watch()
        changes = [
            _change(watch, site_id="123456", site_name="Site A"),
            _change(watch, site_id="789012", site_name="Site B", loop="Loop B",
                    campsite_type="ELECTRIC", new_dates=["2026-06-02"], max_people=8),
        ]

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(return_value=httpx.Response(200))

            await notify_ntfy("test-topic", _result(watch, *changes))

            body = _body(respx_mock.calls[0].request)
            assert "2 sites open at Test Camp" in body
            assert "Site A" in body
            assert "Site B" in body


class TestFormatChangeEdgeCases:
    """Edge case tests for format_change."""

    def test_format_change_exactly_5_dates(self):
        """format_change with exactly 5 dates shows no '+more'."""
        change = _change(_watch(), new_dates=[f"2026-06-0{d}" for d in range(1, 6)])

        formatted = format_change(change)

        assert "+0 more" not in formatted
        assert "Mon Jun 01" in formatted  # June 1, 2026 is Monday
        assert "Fri Jun 05" in formatted  # June 5, 2026 is Friday

    def test_format_change_six_dates(self):
        """format_change with 6 dates shows '+1 more'."""
        change = _change(_watch(), new_dates=[f"2026-06-0{d}" for d in range(1, 7)])

        formatted = format_change(change)

        assert "+1 more" in formatted
        assert "Jun 06" not in formatted


class TestContextualFormatting:
    """Tests for context_message in format_poll_result."""

    def test_format_poll_result_with_context_message(self):
        """When context_message is set, it's used instead of standard header."""
        watch = _watch(name="Ohanapecosh Campground")
        change = _change(watch, context_message="Popular weekend spot just opened!")

        formatted = format_poll_result(_result(watch, change))

        assert "Popular weekend spot just opened!" in formatted
        assert "1 site open at Ohanapecosh Campground" not in formatted

    def test_format_poll_result_without_context_message(self):
        """When context_message is empty, uses standard formatting."""
        watch = _watch(name="Ohanapecosh Campground")

        formatted = format_poll_result(_result(watch, _change(watch, context_message="")))

        assert "1 site open at Ohanapecosh Campground" in formatted

    def test_format_poll_result_context_message_uses_first_change(self):
        """When multiple changes, uses context_message from first change."""
        watch = _watch()
        changes = [
            _change(watch, context_message="First change context"),
            _change(watch, site_id="789012", site_name="A002", context_message="Second change context"),
        ]

        formatted = format_poll_result(_result(watch, *changes))

        assert "First change context" in formatted
        assert "Second change context" not in formatted


class TestNotifyPushover:
    """Tests for Pushover notification dispatch."""

    async def test_notify_pushover_posts_to_api(self) -> None:
        """notify_pushover sends POST to Pushover API with correct data."""
        watch = _watch(name="Ohanapecosh")

        with respx.mock:
            route = respx.post("https://api.pushover.net/1/messages.json").mock(
                return_value=httpx.Response(200, json={"status": 1})
            )

            await notify_pushover(
                user_key="user123", api_token="token123", result=_result(watch, _change(watch)),
            )

            assert route.called
            content = route.calls[0].request.content
            assert b"token=token123" in content
            assert b"user=user123" in content
            assert b"Ohanapecosh" in content

    async def test_notify_pushover_includes_booking_url(self) -> None:
        """notify_pushover includes the recreation.gov booking URL."""
        with respx.mock:
            route = respx.post("https://api.pushover.net/1/messages.json").mock(
                return_value=httpx.Response(200)
            )

            await notify_pushover(user_key="user123", api_token="token123", result=_result())

            assert b"recreation.gov" in route.calls[0].request.content


class TestNotifyWebPush:
    """Tests for web push notification dispatch."""

    async def test_notify_web_push_returns_early_without_key(self, monkeypatch) -> None:
        """notify_web_push returns early if VAPID_PRIVATE_KEY not set."""
        monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)

        await notify_web_push({"endpoint": "https://example.com"}, _result())
