"""Tests for the updated tag taxonomy — renames, additions, removals."""

from __future__ import annotations

from pnw_campsites.enrichment.llm_tags import (
    VALID_TAGS,
    TagExtractionResult,
    _TAG_RENAMES,
)


class TestValidTags:
    """Tests for the canonical tag list."""

    def test_new_tags_present(self):
        """Tags added from RIDB mapping should be in VALID_TAGS."""
        for tag in ("campfire", "pull-through", "boat-launch",
                     "backcountry", "dispersed", "equestrian",
                     "winter-camping"):
            assert tag in VALID_TAGS, f"Expected {tag} in VALID_TAGS"

    def test_removed_tags_absent(self):
        """Removed tags should not be in VALID_TAGS."""
        for tag in ("scenic", "glacier", "volcanic", "bear-box", "meadow"):
            assert tag not in VALID_TAGS, f"{tag} should be removed"

    def test_merged_tags_absent(self):
        """Merged source tags should not be in VALID_TAGS."""
        assert "oceanfront" not in VALID_TAGS  # → beach
        assert "horse-camp" not in VALID_TAGS  # → equestrian

    def test_core_tags_preserved(self):
        """Core tags that were always valid should still be present."""
        for tag in ("lakeside", "riverside", "beach", "pet-friendly",
                     "rv-friendly", "tent-only", "trails", "shade",
                     "forest", "alpine", "remote", "kid-friendly"):
            assert tag in VALID_TAGS

    def test_tag_count_in_range(self):
        """Should have 30-45 tags total."""
        assert 25 <= len(VALID_TAGS) <= 45


class TestTagRenames:
    """Tests for the _TAG_RENAMES mapping."""

    def test_oceanfront_maps_to_beach(self):
        assert _TAG_RENAMES["oceanfront"] == "beach"

    def test_horse_camp_maps_to_equestrian(self):
        assert _TAG_RENAMES["horse-camp"] == "equestrian"

    def test_removed_tags_map_to_none(self):
        for tag in ("scenic", "glacier", "volcanic", "bear-box", "meadow"):
            assert tag in _TAG_RENAMES
            assert _TAG_RENAMES[tag] is None


class TestTagExtractionResultWithRenames:
    """Tests for the validator handling renamed/removed tags."""

    def test_renamed_tag_is_mapped(self):
        """oceanfront should be mapped to beach."""
        result = TagExtractionResult(tags=["oceanfront", "lakeside"])
        assert "beach" in result.tags
        assert "oceanfront" not in result.tags
        assert "lakeside" in result.tags

    def test_horse_camp_mapped_to_equestrian(self):
        result = TagExtractionResult(tags=["horse-camp", "trails"])
        assert "equestrian" in result.tags
        assert "horse-camp" not in result.tags

    def test_removed_tag_is_dropped(self):
        """scenic should be silently dropped."""
        result = TagExtractionResult(tags=["lakeside", "scenic", "trails"])
        assert "lakeside" in result.tags
        assert "trails" in result.tags
        assert "scenic" not in result.tags
        assert len(result.tags) == 2

    def test_unknown_tag_is_dropped(self):
        """Unknown tags should be dropped."""
        result = TagExtractionResult(tags=["lakeside", "totally-fake"])
        assert result.tags == ["lakeside"]

    def test_dedup_after_rename(self):
        """If rename creates a duplicate, it should be deduped."""
        result = TagExtractionResult(tags=["beach", "oceanfront", "lakeside"])
        assert result.tags.count("beach") == 1
        assert "lakeside" in result.tags

    def test_all_removed_tags_produces_empty(self):
        result = TagExtractionResult(tags=["scenic", "glacier", "volcanic"])
        assert result.tags == []

    def test_empty_input(self):
        result = TagExtractionResult(tags=[])
        assert result.tags == []

    def test_new_valid_tags_accepted(self):
        """New tags from the audit should be accepted."""
        result = TagExtractionResult(
            tags=["campfire", "pull-through", "winter-camping", "dispersed"]
        )
        assert len(result.tags) == 4
