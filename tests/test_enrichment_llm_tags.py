"""Tests for LLM-based tag extraction from campground descriptions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.enrichment.llm_tags import (
    VALID_TAGS,
    TagExtractionResult,
    extract_tags,
)


class TestTagExtractionResult:
    """Test the TagExtractionResult Pydantic model."""

    def test_valid_tags_extracted(self):
        """Valid tags from VALID_TAGS list are preserved."""
        result = TagExtractionResult(tags=["lakeside", "scenic", "forest"])
        assert result.tags == ["lakeside", "scenic", "forest"]

    def test_invalid_tags_filtered(self):
        """Invalid tags not in VALID_TAGS are filtered out."""
        result = TagExtractionResult(
            tags=["lakeside", "invalid-tag", "scenic"]
        )
        assert result.tags == ["lakeside", "scenic"]

    def test_empty_tags(self):
        """Empty tag list is valid."""
        result = TagExtractionResult(tags=[])
        assert result.tags == []


class TestExtractTags:
    """Test the extract_tags async function."""

    @pytest.mark.asyncio
    async def test_extract_tags_valid_response(self):
        """Successfully extracts tags from valid API response."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"tags": ["lakeside", "scenic", "forest"]}'
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
            tags = await extract_tags(
                name="Test Lake",
                description="Beautiful campground by a lake with scenic views",
                api_key="test-key",
            )

        assert tags == ["lakeside", "scenic", "forest"]

    @pytest.mark.asyncio
    async def test_extract_tags_short_description(self):
        """Short descriptions (< 20 chars) return empty list."""
        tags = await extract_tags(
            name="Test",
            description="Too short",
            api_key="test-key",
        )
        assert tags == []

    @pytest.mark.asyncio
    async def test_extract_tags_empty_description(self):
        """Empty descriptions return empty list."""
        tags = await extract_tags(
            name="Test",
            description="",
            api_key="test-key",
        )
        assert tags == []

    @pytest.mark.asyncio
    async def test_extract_tags_markdown_code_block(self):
        """Extracts JSON from markdown code block format."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```json\n{"tags": ["lakeside", "scenic"]}\n```'
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
            tags = await extract_tags(
                name="River Camp",
                description="Campground by a river in the mountains",
                api_key="test-key",
            )

        assert sorted(tags) == ["lakeside", "scenic"]

    @pytest.mark.asyncio
    async def test_extract_tags_api_error(self):
        """API errors return empty list."""
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
            tags = await extract_tags(
                name="Test Camp",
                description="A nice campground with many features",
                api_key="test-key",
            )

        assert tags == []

    @pytest.mark.asyncio
    async def test_extract_tags_invalid_json_response(self):
        """Invalid JSON responses return empty list."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not json")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            tags = await extract_tags(
                name="Test Camp",
                description="A nice campground with many features",
                api_key="test-key",
            )

        assert tags == []

    @pytest.mark.asyncio
    async def test_extract_tags_valid_tags_list(self):
        """Checks that VALID_TAGS contains expected tag values."""
        assert "lakeside" in VALID_TAGS
        assert "scenic" in VALID_TAGS
        assert "pet-friendly" in VALID_TAGS
        assert "trails" in VALID_TAGS
        assert len(VALID_TAGS) > 20
