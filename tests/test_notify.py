"""Tests for notification formatters and dispatch (notify.py)."""

from __future__ import annotations

import httpx
import pytest
import respx

from pnw_campsites.monitor.db import Watch
from pnw_campsites.monitor.notify import (
    format_change,
    format_poll_result,
    notify_ntfy,
)
from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult


class TestFormatChange:
    """Tests for format_change formatter."""

    def test_format_change_basic_structure(self):
        """format_change returns human-readable message with site and dates."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            new_dates=["2026-06-01"],
            max_people=6,
        )

        formatted = format_change(change)

        assert "Site A001" in formatted
        assert "Loop A" in formatted
        assert "max 6p" in formatted
        assert "Mon Jun 01" in formatted  # June 1, 2026 is Monday

    def test_format_change_multiple_dates(self):
        """format_change includes first 5 dates, shows count for more."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=[
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
                "2026-06-04",
                "2026-06-05",
                "2026-06-06",
                "2026-06-07",
            ],
            max_people=6,
        )

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
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="Site X",
            loop="Loop B",
            campsite_type="ELECTRIC",
            new_dates=["2026-06-15"],
            max_people=4,
        )

        formatted = format_change(change)

        assert "Site X" in formatted
        assert "Loop B" in formatted
        assert "max 4p" in formatted
        assert "Mon Jun 15" in formatted
        assert "+0 more" not in formatted  # No "more"

    def test_format_change_date_formatting(self):
        """format_change dates are formatted as 'Day Mon DD'."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-12-01",
            end_date="2026-12-31",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-12-25"],  # Christmas (Fri)
            max_people=6,
        )

        formatted = format_change(change)

        assert "Fri Dec 25" in formatted


class TestFormatPollResult:
    """Tests for format_poll_result formatter."""

    def test_format_poll_result_single_change(self):
        """format_poll_result includes watch name, change count, and booking URL."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Ohanapecosh Campground",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            new_dates=["2026-06-01"],
            max_people=6,
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        assert "New availability at Ohanapecosh Campground!" in formatted
        assert "1 site(s) with new dates:" in formatted
        assert "https://www.recreation.gov/camping/campgrounds/232465" in formatted
        assert "startDate=2026-06-01" in formatted

    def test_format_poll_result_multiple_changes(self):
        """format_poll_result shows up to 10 changes, then summary."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        changes = [
            AvailabilityChange(
                watch=watch,
                site_id=f"site{i}",
                site_name=f"Site {i}",
                loop="Loop A",
                campsite_type="STANDARD",
                new_dates=["2026-06-01"],
                max_people=6,
            )
            for i in range(15)
        ]
        result = PollResult(watch=watch, changes=changes)

        formatted = format_poll_result(result)

        assert "15 site(s) with new dates:" in formatted
        assert "Site 0" in formatted
        assert "Site 9" in formatted
        assert "... and 5 more sites" in formatted
        assert "Site 10" not in formatted  # Beyond first 10

    def test_format_poll_result_zero_changes(self):
        """format_poll_result with zero changes still formats."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        result = PollResult(watch=watch, changes=[])

        formatted = format_poll_result(result)

        assert "New availability at Test Camp!" in formatted
        assert "0 site(s) with new dates:" in formatted
        assert "https://www.recreation.gov" in formatted

    def test_format_poll_result_includes_booking_url_with_date(self):
        """format_poll_result booking URL includes start_date param."""
        watch = Watch(
            id=1,
            facility_id="999",
            name="Test Camp",
            start_date="2026-08-15",
            end_date="2026-08-31",
        )
        result = PollResult(watch=watch, changes=[])

        formatted = format_poll_result(result)

        assert "https://www.recreation.gov/camping/campgrounds/999" in formatted
        assert "startDate=2026-08-15" in formatted

    def test_format_poll_result_multi_line(self):
        """format_poll_result output is multi-line with proper structure."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)
        lines = formatted.split("\n")

        # Header, count, blank, site, blank, URL
        assert len(lines) >= 5
        assert "New availability" in lines[0]
        assert "site(s)" in lines[1]
        assert "Book:" in lines[-1]


class TestNotifyNtfy:
    """Tests for notify_ntfy dispatch function."""

    @pytest.mark.asyncio
    async def test_notify_ntfy_posts_to_correct_endpoint(self):
        """notify_ntfy POSTs to ntfy.sh with topic."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
        )
        result = PollResult(watch=watch, changes=[change])

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(
                return_value=httpx.Response(200)
            )

            await notify_ntfy("test-topic", result)

            assert respx_mock.calls.called
            request = respx_mock.calls[0].request
            assert request.method == "POST"
            assert "test-topic" in request.url.path

    @pytest.mark.asyncio
    async def test_notify_ntfy_includes_headers(self):
        """notify_ntfy includes Title, Tags, Click, Priority headers."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="My Campground",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        result = PollResult(watch=watch, changes=[])

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(
                return_value=httpx.Response(200)
            )

            await notify_ntfy("test-topic", result)

            request = respx_mock.calls[0].request
            assert request.headers["Title"] == "Campsite Alert: My Campground"
            assert request.headers["Tags"] == "tent,camping"
            assert "recreation.gov" in request.headers["Click"]
            assert request.headers["Priority"] == "high"

    @pytest.mark.asyncio
    async def test_notify_ntfy_custom_server(self):
        """notify_ntfy respects custom ntfy server parameter."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        result = PollResult(watch=watch, changes=[])

        with respx.mock(base_url="https://ntfy.myserver.com") as respx_mock:
            respx_mock.post("/mytopic").mock(
                return_value=httpx.Response(200)
            )

            await notify_ntfy(
                "mytopic", result, server="https://ntfy.myserver.com"
            )

            request = respx_mock.calls[0].request
            assert "ntfy.myserver.com" in str(request.url)

    @pytest.mark.asyncio
    async def test_notify_ntfy_body_contains_message(self):
        """notify_ntfy POST body contains formatted message."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
        )
        result = PollResult(watch=watch, changes=[change])

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(
                return_value=httpx.Response(200)
            )

            await notify_ntfy("test-topic", result)

            request = respx_mock.calls[0].request
            body = request.content.decode() if isinstance(
                request.content, bytes
            ) else request.content
            assert "New availability at Test Camp" in body
            assert "Site A001" in body

    @pytest.mark.asyncio
    async def test_notify_ntfy_handles_multiple_changes(self):
        """notify_ntfy includes all changes in message."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        changes = [
            AvailabilityChange(
                watch=watch,
                site_id="123456",
                site_name="Site A",
                loop="Loop A",
                campsite_type="STANDARD",
                new_dates=["2026-06-01"],
                max_people=6,
            ),
            AvailabilityChange(
                watch=watch,
                site_id="789012",
                site_name="Site B",
                loop="Loop B",
                campsite_type="ELECTRIC",
                new_dates=["2026-06-02"],
                max_people=8,
            ),
        ]
        result = PollResult(watch=watch, changes=changes)

        with respx.mock(base_url="https://ntfy.sh") as respx_mock:
            respx_mock.post("/test-topic").mock(
                return_value=httpx.Response(200)
            )

            await notify_ntfy("test-topic", result)

            request = respx_mock.calls[0].request
            body = request.content.decode() if isinstance(
                request.content, bytes
            ) else request.content
            assert "2 site(s) with new dates" in body
            assert "Site A" in body
            assert "Site B" in body


class TestFormatChangeEdgeCases:
    """Edge case tests for format_change."""

    def test_format_change_exactly_5_dates(self):
        """format_change with exactly 5 dates shows no '+more'."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=[
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
                "2026-06-04",
                "2026-06-05",
            ],
            max_people=6,
        )

        formatted = format_change(change)

        assert "+0 more" not in formatted
        assert "Mon Jun 01" in formatted  # June 1, 2026 is Monday
        assert "Fri Jun 05" in formatted  # June 5, 2026 is Friday

    def test_format_change_six_dates(self):
        """format_change with 6 dates shows '+1 more'."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=[
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
                "2026-06-04",
                "2026-06-05",
                "2026-06-06",
            ],
            max_people=6,
        )

        formatted = format_change(change)

        assert "+1 more" in formatted
        assert "Jun 06" not in formatted


class TestContextualFormatting:
    """Tests for context_message and urgency in format_poll_result."""

    def test_format_poll_result_with_context_message(self):
        """When context_message is set, it's used instead of standard header."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Ohanapecosh Campground",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            new_dates=["2026-06-01"],
            max_people=6,
            context_message="Popular weekend spot just opened!",
            urgency=3,
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        assert "Popular weekend spot just opened!" in formatted
        assert "New availability at Ohanapecosh Campground!" not in formatted

    def test_format_poll_result_without_context_message(self):
        """When context_message is empty, uses standard formatting."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Ohanapecosh Campground",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            new_dates=["2026-06-01"],
            max_people=6,
            context_message="",  # Empty context_message
            urgency=2,
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        assert "New availability at Ohanapecosh Campground!" in formatted

    def test_format_poll_result_urgency_3_includes_fire_emoji(self):
        """Urgency 3 includes fire emoji prefix when context_message is set."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Popular Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
            context_message="Peak weekend availability opened!",
            urgency=3,  # High urgency
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        # Should include fire emoji (U+1F525)
        assert "\U0001f525" in formatted
        assert "Peak weekend availability opened!" in formatted

    def test_format_poll_result_urgency_1_no_prefix(self):
        """Urgency 1 has no emoji prefix when context_message is set."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Quiet Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
            context_message="Midweek campground opening.",
            urgency=1,  # Low urgency
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        # Should NOT include fire emoji
        assert "\U0001f525" not in formatted
        assert "Midweek campground opening." in formatted

    def test_format_poll_result_urgency_2_no_prefix(self):
        """Urgency 2 has no emoji prefix when context_message is set."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Standard Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        change = AvailabilityChange(
            watch=watch,
            site_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            new_dates=["2026-06-01"],
            max_people=6,
            context_message="Sites now available.",
            urgency=2,  # Standard urgency
        )
        result = PollResult(watch=watch, changes=[change])

        formatted = format_poll_result(result)

        # Should NOT include fire emoji
        assert "\U0001f525" not in formatted
        assert "Sites now available." in formatted

    def test_format_poll_result_context_message_uses_first_change(self):
        """When multiple changes, uses context_message from first change."""
        watch = Watch(
            id=1,
            facility_id="232465",
            name="Test Camp",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
        changes = [
            AvailabilityChange(
                watch=watch,
                site_id="123456",
                site_name="A001",
                loop="Loop A",
                campsite_type="STANDARD",
                new_dates=["2026-06-01"],
                max_people=6,
                context_message="First change context",
                urgency=3,
            ),
            AvailabilityChange(
                watch=watch,
                site_id="789012",
                site_name="A002",
                loop="Loop B",
                campsite_type="ELECTRIC",
                new_dates=["2026-06-02"],
                max_people=8,
                context_message="Second change context",
                urgency=2,
            ),
        ]
        result = PollResult(watch=watch, changes=changes)

        formatted = format_poll_result(result)

        assert "First change context" in formatted
        assert "Second change context" not in formatted
        assert "\U0001f525" in formatted  # Uses first change urgency (3)
