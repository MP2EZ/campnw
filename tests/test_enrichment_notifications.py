"""Tests for LLM-enriched notification messages (notifications.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.enrichment.notifications import enrich_notification

try:
    import anthropic  # noqa: F401
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

needs_anthropic = pytest.mark.skipif(
    not HAS_ANTHROPIC, reason="anthropic package not installed",
)


@needs_anthropic
class TestEnrichNotification:
    """Test the enrich_notification async function."""

    @pytest.mark.asyncio
    async def test_enrich_notification_valid_response(self):
        """Successfully returns (message, urgency) from valid API response."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"message": "Popular weekend spot just opened!", "urgency": 3}'
            )
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Lake Sammamish",
                site_count=3,
                dates=["2026-06-13", "2026-06-14"],
                api_key="test-key",
            )

        assert message == "Popular weekend spot just opened!"
        assert urgency == 3

    @pytest.mark.asyncio
    async def test_enrich_notification_urgency_clamped_to_range(self):
        """Urgency is clamped to 1-3 range."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"message": "Sites available", "urgency": 10}')
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Test Camp",
                site_count=1,
                dates=["2026-06-10"],
                api_key="test-key",
            )

        assert urgency == 3  # Clamped from 10

    @pytest.mark.asyncio
    async def test_enrich_notification_low_urgency_clamped(self):
        """Urgency below 1 is clamped to 1."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"message": "Midweek availability", "urgency": -5}')
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Test Camp",
                site_count=1,
                dates=["2026-06-10"],
                api_key="test-key",
            )

        assert urgency == 1  # Clamped from -5

    @pytest.mark.asyncio
    async def test_enrich_notification_no_api_key_returns_fallback(self):
        """Missing API key returns fallback message with urgency 2."""
        message, urgency = await enrich_notification(
            campground_name="Lake Camp",
            site_count=2,
            dates=["2026-06-15"],
            api_key="",
        )

        assert message == "2 sites open at Lake Camp"
        assert urgency == 2

    @pytest.mark.asyncio
    async def test_enrich_notification_api_error_returns_fallback(self):
        """API errors return fallback message."""
        import anthropic

        mock_request = MagicMock()
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIError(
                "API Error", mock_request, body=None
            )
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="River Camp",
                site_count=1,
                dates=["2026-07-01"],
                api_key="test-key",
            )

        assert message == "1 site open at River Camp"
        assert urgency == 2

    @pytest.mark.asyncio
    async def test_enrich_notification_invalid_json_returns_fallback(self):
        """Invalid JSON response falls back to simple message."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Test Camp",
                site_count=5,
                dates=["2026-06-20"],
                api_key="test-key",
            )

        assert message == "5 sites open at Test Camp"
        assert urgency == 2

    @pytest.mark.asyncio
    async def test_enrich_notification_json_in_markdown_block(self):
        """Extracts JSON from markdown code block format."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```json\n{"message": "Peak weekend availability!", '
                '"urgency": 3}\n```'
            )
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Popular Park",
                site_count=4,
                dates=["2026-06-13", "2026-06-14"],
                api_key="test-key",
            )

        assert message == "Peak weekend availability!"
        assert urgency == 3

    @pytest.mark.asyncio
    async def test_enrich_notification_missing_message_returns_fallback(self):
        """Response without message field returns fallback."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"urgency": 2}')  # No message
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            message, urgency = await enrich_notification(
                campground_name="Test Camp",
                site_count=1,
                dates=["2026-06-10"],
                api_key="test-key",
            )

        assert message == "1 site open at Test Camp"
        assert urgency == 2

    @pytest.mark.asyncio
    async def test_enrich_notification_date_formatting_in_prompt(self):
        """Dates are formatted and passed to the LLM."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"message": "Sites available", "urgency": 2}'
            )
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            dates = [f"2026-06-{d:02d}" for d in range(10, 15)]
            message, urgency = await enrich_notification(
                campground_name="Test Camp",
                site_count=5,
                dates=dates,
                api_key="test-key",
            )

        # Verify dates were in the prompt
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        prompt_text = messages[0]["content"]

        assert "2026-06-10" in prompt_text
        assert "2026-06-14" in prompt_text
        assert message == "Sites available"
        assert urgency == 2

    @pytest.mark.asyncio
    async def test_enrich_notification_many_dates_truncated(self):
        """More than 14 dates shows "+N more" in the prompt."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"message": "Many dates open", "urgency": 3}'
            )
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            # Create 20 dates
            dates = [f"2026-06-{d:02d}" for d in range(1, 21)]
            message, urgency = await enrich_notification(
                campground_name="Busy Camp",
                site_count=10,
                dates=dates,
                api_key="test-key",
            )

        # Verify prompt includes date truncation notice
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        prompt_text = messages[0]["content"]

        assert "(+6 more)" in prompt_text
        assert message == "Many dates open"
        assert urgency == 3
