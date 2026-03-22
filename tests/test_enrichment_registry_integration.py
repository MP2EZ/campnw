"""Integration tests for enrichment with CampgroundRegistry."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from pnw_campsites.enrichment.llm_tags import enrich_registry
from pnw_campsites.registry.models import BookingSystem, Campground


class TestEnrichRegistryIntegration:
    """Test enrich_registry function with real registry."""

    @pytest.mark.asyncio
    async def test_enrich_registry_updates_tags(self, registry):
        """Enrich registry adds extracted tags to campgrounds."""
        # Add a campground with no tags
        cg = Campground(
            facility_id="test-123",
            name="Test Lake Campground",
            booking_system=BookingSystem.RECGOV,
            state="WA",
            notes="Beautiful lake with scenic views and trails",
            tags=[],
            enabled=True,
        )
        registry.upsert(cg)

        # Mock extract_tags to return some tags
        mock_tags = ["lakeside", "scenic", "trails"]

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=mock_tags,
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path),
                api_key="test-key",
                limit=10,
                dry_run=False,
            )

        assert enriched == 1

        # Verify tags were updated in registry
        updated_cg = registry.get_by_facility_id(
            "test-123", BookingSystem.RECGOV
        )
        assert sorted(updated_cg.tags) == sorted(mock_tags)

    @pytest.mark.asyncio
    async def test_enrich_registry_dry_run(self, registry):
        """Dry-run mode doesn't save tags to registry."""
        # Add a campground with no tags
        cg = Campground(
            facility_id="test-456",
            name="Test Mountain Camp",
            booking_system=BookingSystem.RECGOV,
            state="OR",
            notes="High elevation with alpine meadows",
            tags=[],
            enabled=True,
        )
        registry.upsert(cg)

        mock_tags = ["alpine", "meadow"]

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=mock_tags,
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path),
                api_key="test-key",
                limit=10,
                dry_run=True,
            )

        assert enriched == 1

        # Verify tags were NOT saved in registry (still empty)
        updated_cg = registry.get_by_facility_id(
            "test-456", BookingSystem.RECGOV
        )
        assert updated_cg.tags == []

    @pytest.mark.asyncio
    async def test_enrich_registry_skips_existing_tags(self, registry):
        """Campgrounds with existing tags are skipped."""
        # Add a campground WITH tags
        cg = Campground(
            facility_id="test-789",
            name="River Camp",
            booking_system=BookingSystem.RECGOV,
            state="ID",
            notes="River campground",
            tags=["riverside"],
            enabled=True,
        )
        registry.upsert(cg)

        # Add one without tags
        cg2 = Campground(
            facility_id="test-999",
            name="Forest Camp",
            booking_system=BookingSystem.RECGOV,
            state="WA",
            notes="Forest campground",
            tags=[],
            enabled=True,
        )
        registry.upsert(cg2)

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=["forest", "shade"],
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path),
                api_key="test-key",
                limit=10,
                dry_run=False,
            )

        # Only the one without tags should be enriched
        assert enriched == 1

    @pytest.mark.asyncio
    async def test_enrich_registry_respects_limit(self, registry):
        """Enrich registry respects limit parameter."""
        # Add 5 campgrounds with no tags
        for i in range(5):
            cg = Campground(
                facility_id=f"test-{i}",
                name=f"Camp {i}",
                booking_system=BookingSystem.RECGOV,
                state="WA",
                notes="Test campground",
                tags=[],
                enabled=True,
            )
            registry.upsert(cg)

        with patch(
            "pnw_campsites.enrichment.llm_tags.extract_tags",
            new_callable=AsyncMock,
            return_value=["scenic"],
        ):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path),
                api_key="test-key",
                limit=2,  # Only enrich 2 even though 5 are available
                dry_run=False,
            )

        assert enriched == 2

    @pytest.mark.asyncio
    async def test_enrich_registry_no_api_key(self, registry):
        """Missing ANTHROPIC_API_KEY returns 0."""
        # Test with api_key=None and no env var
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            enriched = await enrich_registry(
                registry_path=str(registry._db_path),
                api_key=None,
                limit=10,
                dry_run=False,
            )

        assert enriched == 0
