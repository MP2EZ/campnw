"""Integration tests for enrichment with CampgroundRegistry."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from pnw_campsites.enrichment.llm_tags import enrich_registry
from pnw_campsites.registry.models import BookingSystem, Campground

try:
    import anthropic  # noqa: F401
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def _add(registry, facility_id: str, name: str, **kw) -> None:
    registry.upsert(Campground(
        facility_id=facility_id, name=name, booking_system=BookingSystem.RECGOV, **kw,
    ))


@pytest.mark.skipif(not HAS_ANTHROPIC, reason="anthropic not installed")
class TestEnrichRegistryIntegration:
    """Test enrich_registry function with real registry."""

    async def test_enrich_registry_updates_tags(self, registry):
        """Enrich registry adds extracted tags to campgrounds."""
        _add(registry, "test-123", "Test Lake Campground", state="WA",
             notes="Beautiful lake with scenic views and trails")
        mock_tags = ["lakeside", "scenic", "trails"]

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=mock_tags,
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path), api_key="test-key", limit=10,
            )

        assert enriched == 1
        updated_cg = registry.get_by_facility_id("test-123", BookingSystem.RECGOV)
        assert sorted(updated_cg.tags) == sorted(mock_tags)

    async def test_enrich_registry_dry_run(self, registry):
        """Dry-run mode doesn't save tags to registry."""
        _add(registry, "test-456", "Test Mountain Camp", state="OR",
             notes="High elevation with alpine meadows")

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=["alpine", "meadow"],
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path), api_key="test-key", limit=10, dry_run=True,
            )

        assert enriched == 1
        assert registry.get_by_facility_id("test-456", BookingSystem.RECGOV).tags == []

    async def test_enrich_registry_skips_existing_tags(self, registry):
        """Campgrounds with existing tags are skipped."""
        _add(registry, "test-789", "River Camp", state="ID", notes="River campground", tags=["riverside"])
        _add(registry, "test-999", "Forest Camp", state="WA", notes="Forest campground")

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=["forest", "shade"],
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path), api_key="test-key", limit=10,
            )

        assert enriched == 1

    async def test_enrich_registry_respects_limit(self, registry):
        """Enrich registry respects limit parameter."""
        for i in range(5):
            _add(registry, f"test-{i}", f"Camp {i}", state="WA", notes="Test campground")

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=["scenic"],
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path), api_key="test-key", limit=2,
            )

        assert enriched == 2

    async def test_enrich_registry_no_api_key(self, registry):
        """Missing ANTHROPIC_API_KEY returns 0."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path), api_key=None, limit=10,
            )

        assert enriched == 0
