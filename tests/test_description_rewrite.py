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

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test Lake Camp",
                tags=["lakeside", "kid-friendly"],
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

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], total_sites=10,
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

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result["elevator_pitch"] == "Great camp."

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self):
        """Should return empty dict on API failure."""
        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API error")

            result = await generate_description(
                name="Test", tags=[], total_sites=10,
                state="WA", notes="", api_key="test-key",
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_malformed_json(self):
        """Should return empty dict on unparseable response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], total_sites=10,
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

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_description(
                name="Test", tags=[], total_sites=10,
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

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            await generate_description(
                name="Test", tags=[], total_sites=10,
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


# ---------------------------------------------------------------------------
# regenerate_descriptions (enrich --only-pitch)
# ---------------------------------------------------------------------------


class TestRegenerateDescriptions:
    """--only-pitch overwrites existing copy and exports the pitch fixture."""

    @staticmethod
    def _seed(registry: CampgroundRegistry) -> None:
        for fid, pitch in (("1", "Peaceful haven for solitude seekers."), ("2", "")):
            registry.upsert(Campground(
                facility_id=fid, name=f"Camp {fid}", booking_system=BookingSystem.RECGOV,
                state="WA", tags=["lakeside"], enabled=True,
            ))
            cg = registry.get_by_facility_id(fid, BookingSystem.RECGOV)
            registry.update_vibe(cg.id, "Serene escape")
            if pitch:
                registry.update_description(cg.id, pitch, "Old desc.", "Solitude seekers")

    @staticmethod
    def _fake(by_name: dict[str, dict]):
        async def fake(name, *args, usage=None, **kwargs):
            if usage is not None:
                usage["input_tokens"] += 100
                usage["output_tokens"] += 20
            return by_name.get(name, {})
        return fake

    @pytest.mark.asyncio
    async def test_overwrites_and_exports(self, registry, tmp_path):
        from pnw_campsites.enrichment.llm_tags import regenerate_descriptions
        from pnw_campsites.registry.pitch_fixture import FIXTURE_PATH

        self._seed(registry)
        new = {
            f"Camp {i}": {
                "elevator_pitch": f"Lakeside camp {i}.",
                "description_rewrite": f"Desc {i}.", "best_for": "anglers",
            }
            for i in ("1", "2")
        }
        out = tmp_path / "pitches.json"
        before = FIXTURE_PATH.read_bytes() if FIXTURE_PATH.exists() else None
        with patch("pnw_campsites.enrichment.llm_tags.generate_description", self._fake(new)):
            rewritten, failed, usage = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k", export_path=out,
            )

        assert (rewritten, failed) == (2, 0)
        assert usage == {"input_tokens": 200, "output_tokens": 40}
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert (cg.elevator_pitch, cg.description_rewrite, cg.best_for) == (
            "Lakeside camp 1.", "Desc 1.", "anglers",
        )
        assert cg.tags == ["lakeside"] and cg.vibe == "Serene escape"
        rows = json.loads(out.read_text())["pitches"]
        assert [r["elevator_pitch"] for r in rows] == ["Lakeside camp 1.", "Lakeside camp 2."]
        # The checked-in fixture is only written when asked for.
        assert (FIXTURE_PATH.read_bytes() if FIXTURE_PATH.exists() else None) == before

    @pytest.mark.asyncio
    async def test_failure_keeps_old_copy(self, registry):
        from pnw_campsites.enrichment.llm_tags import regenerate_descriptions

        self._seed(registry)
        with patch("pnw_campsites.enrichment.llm_tags.generate_description", self._fake({})):
            rewritten, failed, _ = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k",
            )

        assert (rewritten, failed) == (0, 2)
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Peaceful haven for solitude seekers."

    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self, registry, tmp_path):
        from pnw_campsites.enrichment.llm_tags import regenerate_descriptions

        self._seed(registry)
        new = {"Camp 1": {"elevator_pitch": "New.", "description_rewrite": "", "best_for": ""}}
        out = tmp_path / "pitches.json"
        with patch("pnw_campsites.enrichment.llm_tags.generate_description", self._fake(new)):
            rewritten, _, _ = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k", dry_run=True,
                export_path=out, limit=1,
            )

        assert rewritten == 1
        assert not out.exists()
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Peaceful haven for solitude seekers."
