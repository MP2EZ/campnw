"""Tests for registry description rewrite (elevator_pitch, description_rewrite, best_for)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.enrichment.llm_tags import generate_description
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground


# ---------------------------------------------------------------------------
# generate_description tests
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    """Tests for the LLM description generation function."""

    @pytest.mark.asyncio
    async def test_returns_three_fields(self):
        """Should return elevator_pitch, description_rewrite, best_for."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({
                "elevator_pitch": "Lakeside camping with mountain views.",
                "description_rewrite": "A beautiful lakeside campground with views of Mt. Rainier. Perfect for families with water activities and short trails.",
                "best_for": "Families with young kids",
            })
        )]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test Lake Camp",
                tags=["lakeside", "kid-friendly"],
                vibe="Perfect for families",
                total_sites=30,
                state="WA",
                notes="Lakeside campground near Rainier",
                api_key="test-key",
            )

        assert "elevator_pitch" in result
        assert "description_rewrite" in result
        assert "best_for" in result
        assert len(result["elevator_pitch"]) > 0

    @pytest.mark.asyncio
    async def test_enforces_length_limits(self):
        """Should truncate fields to max lengths."""
        long_pitch = "A" * 200
        long_desc = "B" * 500
        long_best = "C" * 100

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({
                "elevator_pitch": long_pitch,
                "description_rewrite": long_desc,
                "best_for": long_best,
            })
        )]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert len(result["elevator_pitch"]) <= 120
        assert len(result["description_rewrite"]) <= 350
        assert len(result["best_for"]) <= 50

    @pytest.mark.asyncio
    async def test_handles_markdown_code_blocks(self):
        """Should strip markdown code blocks from response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='```json\n{"elevator_pitch": "Great camp.", "description_rewrite": "Nice place.", "best_for": "everyone"}\n```'
        )]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result["elevator_pitch"] == "Great camp."

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self):
        """Should return empty dict on API failure."""
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API error")

            result = await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_malformed_json(self):
        """Should return empty dict on unparseable response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_missing_fields_in_response(self):
        """Should handle partial JSON response gracefully."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='{"elevator_pitch": "Nice camp."}'
        )]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result["elevator_pitch"] == "Nice camp."
        assert result["description_rewrite"] == ""
        assert result["best_for"] == ""

    @pytest.mark.asyncio
    async def test_uses_haiku_model(self):
        """Should use Haiku, not Sonnet."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='{"elevator_pitch": "x", "description_rewrite": "y", "best_for": "z"}'
        )]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            await generate_description(
                name="Test", tags=[], vibe="", total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

            call_kwargs = mock_client.messages.create.call_args[1]
            assert "haiku" in call_kwargs["model"]


# ---------------------------------------------------------------------------
# Registry schema tests for new columns
# ---------------------------------------------------------------------------


class TestRegistryDescriptionColumns:
    """Tests for the new description columns in the registry."""

    def test_migration_adds_columns(self, tmp_path):
        """Registry init should add elevator_pitch, description_rewrite, best_for."""
        db_path = str(tmp_path / "test.db")
        reg = CampgroundRegistry(db_path)

        cols = {
            row[1]
            for row in reg._conn.execute(
                "PRAGMA table_info(campgrounds)"
            ).fetchall()
        }
        assert "elevator_pitch" in cols
        assert "description_rewrite" in cols
        assert "best_for" in cols
        reg.close()

    def test_update_description(self, tmp_path):
        """update_description should write and persist all three fields."""
        db_path = str(tmp_path / "test.db")
        reg = CampgroundRegistry(db_path)

        cg = reg.upsert(Campground(
            facility_id="test-1",
            name="Test Camp",
            booking_system=BookingSystem.RECGOV,
        ))

        reg.update_description(
            cg.id,
            "Great lakeside spot.",
            "A wonderful campground by the lake with views of the mountains.",
            "Families with kids",
        )

        updated = reg.get_by_id(cg.id)
        assert updated.elevator_pitch == "Great lakeside spot."
        assert "wonderful campground" in updated.description_rewrite
        assert updated.best_for == "Families with kids"
        reg.close()

    def test_upsert_preserves_descriptions(self, tmp_path):
        """Re-upserting should not overwrite existing descriptions."""
        db_path = str(tmp_path / "test.db")
        reg = CampgroundRegistry(db_path)

        cg = reg.upsert(Campground(
            facility_id="test-1",
            name="Test Camp",
            booking_system=BookingSystem.RECGOV,
        ))
        reg.update_description(cg.id, "Pitch", "Desc", "Best")

        # Re-upsert (simulating re-seeding)
        reg.upsert(Campground(
            facility_id="test-1",
            name="Test Camp Updated",
            booking_system=BookingSystem.RECGOV,
        ))

        updated = reg.get_by_id(cg.id)
        # Description fields should be preserved (not overwritten by empty defaults)
        assert updated.elevator_pitch == "Pitch"
        assert updated.description_rewrite == "Desc"
        assert updated.best_for == "Best"
        reg.close()

    def test_model_has_new_fields(self):
        """Campground model should have the new description fields."""
        cg = Campground(
            facility_id="test",
            name="Test",
            booking_system=BookingSystem.RECGOV,
            elevator_pitch="A pitch",
            description_rewrite="A description",
            best_for="Everyone",
        )
        assert cg.elevator_pitch == "A pitch"
        assert cg.description_rewrite == "A description"
        assert cg.best_for == "Everyone"

    def test_model_defaults_to_empty_strings(self):
        """New fields should default to empty strings."""
        cg = Campground(
            facility_id="test",
            name="Test",
            booking_system=BookingSystem.RECGOV,
        )
        assert cg.elevator_pitch == ""
        assert cg.description_rewrite == ""
        assert cg.best_for == ""
