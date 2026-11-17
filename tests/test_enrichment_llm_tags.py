"""Tests for LLM-based tag extraction from campground descriptions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pnw_campsites.enrichment.llm_tags import (
    TagExtractionResult,
    extract_tags,
    generate_vibe,
)


@pytest.fixture
def llm_reply(monkeypatch):
    """Patch the LLM client; `llm_reply(text)` or `llm_reply(error=exc)` returns the mock client."""

    def _install(text: str | None = None, error: Exception | None = None) -> AsyncMock:
        client = AsyncMock()
        if error is not None:
            client.messages.create = AsyncMock(side_effect=error)
        else:
            response = MagicMock()
            response.content = [MagicMock(text=text)]
            client.messages.create = AsyncMock(return_value=response)
        monkeypatch.setattr("pnw_campsites.posthog_client.get_anthropic_client", lambda api_key: client)
        return client

    return _install


async def _tags(description="A nice campground with many features", name="Test Camp"):
    return await extract_tags(name=name, description=description, api_key="test-key")


async def _vibe(name="Test Camp", tags=(), site_count=None, description="Test description"):
    return await generate_vibe(
        name=name, tags=list(tags), site_count=site_count, description=description, api_key="test-key",
    )


class TestTagExtractionResult:
    """Test the TagExtractionResult Pydantic model."""

    def test_valid_tags_extracted(self):
        """Valid tags from VALID_TAGS list are preserved."""
        result = TagExtractionResult(tags=["lakeside", "shade", "forest"])
        assert result.tags == ["lakeside", "shade", "forest"]

    def test_invalid_tags_filtered(self):
        """Invalid tags not in VALID_TAGS are filtered out."""
        result = TagExtractionResult(tags=["lakeside", "invalid-tag", "shade"])
        assert result.tags == ["lakeside", "shade"]

    def test_empty_tags(self):
        """Empty tag list is valid."""
        result = TagExtractionResult(tags=[])
        assert result.tags == []


class TestExtractTags:
    """Test the extract_tags async function."""

    async def test_extract_tags_valid_response(self, llm_reply):
        llm_reply('{"tags": ["lakeside", "shade", "forest"]}')

        assert await _tags("Beautiful campground by a lake with scenic views") == ["lakeside", "shade", "forest"]

    async def test_extract_tags_short_description(self):
        """Short descriptions (< 20 chars) return empty list."""
        assert await _tags("Too short") == []

    async def test_extract_tags_empty_description(self):
        """Empty descriptions return empty list."""
        assert await _tags("") == []

    async def test_extract_tags_markdown_code_block(self, llm_reply):
        """Extracts JSON from markdown code block format."""
        llm_reply('```json\n{"tags": ["lakeside", "shade"]}\n```')

        assert sorted(await _tags("Campground by a river in the mountains")) == ["lakeside", "shade"]

    async def test_extract_tags_api_error(self, llm_reply):
        """API errors return empty list."""
        llm_reply(error=RuntimeError("API Error"))

        assert await _tags() == []

    async def test_extract_tags_invalid_json_response(self, llm_reply):
        """Invalid JSON responses return empty list."""
        llm_reply("not json")

        assert await _tags() == []


class TestGenerateVibe:
    """Test the generate_vibe async function."""

    async def test_generate_vibe_valid_response(self, llm_reply):
        llm_reply("Beautiful lakeside campground for families")

        assert await _vibe("Lake Camp", ["lakeside", "kid-friendly"], 50) == "Beautiful lakeside campground for families"

    async def test_generate_vibe_truncates_long_response(self, llm_reply):
        """Long responses are truncated to 100 chars."""
        llm_reply("A" * 150)

        assert len(await _vibe()) <= 100

    async def test_generate_vibe_strips_quotes(self, llm_reply):
        """Response with surrounding quotes has them stripped."""
        llm_reply('"Beautiful forest retreat"')

        assert await _vibe("Forest Camp", ["forest"], 30) == "Beautiful forest retreat"

    async def test_generate_vibe_api_error_returns_empty_string(self, llm_reply):
        """API errors return empty string gracefully."""
        llm_reply(error=RuntimeError("API Error"))

        assert await _vibe() == ""

    async def test_generate_vibe_includes_tags_in_prompt(self, llm_reply):
        """Tags and site_count are interpolated into the LLM prompt."""
        client = llm_reply("Great campground")

        vibe = await _vibe("Alpine Camp", ["alpine", "shade", "hiking"], 20, "High altitude alpine camp")

        prompt_text = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Tags: alpine, shade, hiking." in prompt_text
        assert "It has 20 sites." in prompt_text
        assert vibe == "Great campground"
