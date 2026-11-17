"""Tests for registry description rewrite (elevator_pitch, description_rewrite, best_for)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.enrichment.llm_tags import generate_description, regenerate_descriptions
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.registry.pitch_fixture import FIXTURE_PATH


@pytest.fixture
def llm_client():
    """Patch the PostHog-wrapped Anthropic client; returns the mock client."""
    with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value = client
        yield client


def _reply(client: AsyncMock, text: str) -> None:
    client.messages.create.return_value = MagicMock(content=[MagicMock(text=text)])


async def _generate(**kw):
    args = {"name": "Test", "tags": [], "total_sites": 10, "state": "WA", "notes": "", "api_key": "test-key"}
    return await generate_description(**{**args, **kw})


class TestGenerateDescription:
    """Tests for the LLM description generation function."""

    async def test_returns_three_fields(self, llm_client):
        """Should return elevator_pitch, description_rewrite, best_for."""
        _reply(llm_client, json.dumps({
            "elevator_pitch": "Lakeside camping with mountain views.",
            "description_rewrite": "A beautiful lakeside campground with views of Mt. Rainier. Perfect for families with water activities and short trails.",
            "best_for": "Families with young kids",
        }))

        result = await _generate(
            name="Test Lake Camp", tags=["lakeside", "kid-friendly"], total_sites=30,
            notes="Lakeside campground near Rainier",
        )

        assert "elevator_pitch" in result
        assert "description_rewrite" in result
        assert "best_for" in result
        assert len(result["elevator_pitch"]) > 0

    async def test_enforces_length_limits(self, llm_client):
        """Should truncate fields to max lengths."""
        _reply(llm_client, json.dumps({
            "elevator_pitch": "A" * 200,
            "description_rewrite": "B" * 500,
            "best_for": "C" * 100,
        }))

        result = await _generate()

        assert len(result["elevator_pitch"]) <= 120
        assert len(result["description_rewrite"]) <= 350
        assert len(result["best_for"]) <= 50

    async def test_handles_markdown_code_blocks(self, llm_client):
        """Should strip markdown code blocks from response."""
        _reply(
            llm_client,
            '```json\n{"elevator_pitch": "Great camp.", "description_rewrite": "Nice place.", "best_for": "everyone"}\n```',
        )

        assert (await _generate())["elevator_pitch"] == "Great camp."

    async def test_returns_empty_on_api_error(self, llm_client):
        """Should return empty dict on API failure."""
        llm_client.messages.create.side_effect = Exception("API error")

        assert await _generate() == {}

    async def test_returns_empty_on_malformed_json(self, llm_client):
        """Should return empty dict on unparseable response."""
        _reply(llm_client, "Not valid JSON at all")

        assert await _generate() == {}

    async def test_handles_missing_fields_in_response(self, llm_client):
        """Should handle partial JSON response gracefully."""
        _reply(llm_client, '{"elevator_pitch": "Nice camp."}')

        result = await _generate()

        assert result["elevator_pitch"] == "Nice camp."
        assert result["description_rewrite"] == ""
        assert result["best_for"] == ""

    async def test_uses_haiku_model(self, llm_client):
        """Should use Haiku, not Sonnet."""
        _reply(llm_client, '{"elevator_pitch": "x", "description_rewrite": "y", "best_for": "z"}')

        await _generate()

        assert "haiku" in llm_client.messages.create.call_args[1]["model"]


class TestRegistryDescriptionColumns:
    """Tests for the description columns in the registry."""

    def test_update_description(self, registry):
        """update_description should write and persist all three fields."""
        cg = registry.upsert(Campground(
            facility_id="test-1",
            name="Test Camp",
            booking_system=BookingSystem.RECGOV,
        ))

        registry.update_description(
            cg.id,
            "Great lakeside spot.",
            "A wonderful campground by the lake with views of the mountains.",
            "Families with kids",
        )

        updated = registry.get_by_id(cg.id)
        assert updated.elevator_pitch == "Great lakeside spot."
        assert "wonderful campground" in updated.description_rewrite
        assert updated.best_for == "Families with kids"

    def test_upsert_preserves_descriptions(self, registry):
        """Re-upserting should not overwrite existing descriptions."""
        cg = registry.upsert(Campground(
            facility_id="test-1",
            name="Test Camp",
            booking_system=BookingSystem.RECGOV,
        ))
        registry.update_description(cg.id, "Pitch", "Desc", "Best")

        # Re-seeding must not blank the copy
        registry.upsert(Campground(
            facility_id="test-1",
            name="Test Camp Updated",
            booking_system=BookingSystem.RECGOV,
        ))

        updated = registry.get_by_id(cg.id)
        assert updated.elevator_pitch == "Pitch"
        assert updated.description_rewrite == "Desc"
        assert updated.best_for == "Best"


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
        # Nothing but a name and a state: copy written from that is invented.
        registry.upsert(Campground(
            facility_id="3", name="Camp 3", booking_system=BookingSystem.RECGOV,
            state="CA", enabled=True,
        ))
        cg = registry.get_by_facility_id("3", BookingSystem.RECGOV)
        registry.update_description(cg.id, "Rustic charm for nature lovers.", "Old.", "Lovers")

    @staticmethod
    def _fake(by_name: dict[str, dict]):
        async def fake(name, *args, usage=None, **kwargs):
            if usage is not None:
                usage["input_tokens"] += 100
                usage["output_tokens"] += 20
            return by_name.get(name, {})
        return fake

    async def test_overwrites_and_exports(self, registry, tmp_path):
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
            rewritten, cleared, failed, usage = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k", export_path=out,
            )

        assert (rewritten, cleared, failed) == (2, 1, 0)
        assert usage == {"input_tokens": 200, "output_tokens": 40}  # no call for Camp 3
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert (cg.elevator_pitch, cg.description_rewrite, cg.best_for) == (
            "Lakeside camp 1.", "Desc 1.", "anglers",
        )
        assert cg.tags == ["lakeside"] and cg.vibe == "Serene escape"
        rows = json.loads(out.read_text())["pitches"]
        assert [r["elevator_pitch"] for r in rows] == ["Lakeside camp 1.", "Lakeside camp 2.", ""]
        none = registry.get_by_facility_id("3", BookingSystem.RECGOV)
        assert (none.elevator_pitch, none.description_rewrite, none.best_for) == ("", "", "")
        # The checked-in fixture is only written when asked for.
        assert (FIXTURE_PATH.read_bytes() if FIXTURE_PATH.exists() else None) == before

    async def test_failure_keeps_old_copy(self, registry):
        self._seed(registry)
        with patch("pnw_campsites.enrichment.llm_tags.generate_description", self._fake({})):
            rewritten, _, failed, _ = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k",
            )

        assert (rewritten, failed) == (0, 2)
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Peaceful haven for solitude seekers."

    async def test_dry_run_writes_nothing(self, registry, tmp_path):
        self._seed(registry)
        new = {"Camp 1": {"elevator_pitch": "New.", "description_rewrite": "", "best_for": ""}}
        out = tmp_path / "pitches.json"
        with patch("pnw_campsites.enrichment.llm_tags.generate_description", self._fake(new)):
            rewritten, cleared, _, _ = await regenerate_descriptions(
                registry_path=str(registry._db_path), api_key="k", dry_run=True,
                export_path=out,
            )

        assert (rewritten, cleared) == (1, 1)
        assert not out.exists()
        cg = registry.get_by_facility_id("1", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Peaceful haven for solitude seekers."
        cg = registry.get_by_facility_id("3", BookingSystem.RECGOV)
        assert cg.elevator_pitch == "Rustic charm for nature lovers."
