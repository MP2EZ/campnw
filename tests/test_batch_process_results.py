"""Tests for batch.process_results() — enrichment result processing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from pnw_campsites.enrichment.batch import process_results
from pnw_campsites.registry.models import BookingSystem
from tests.conftest import make_campground

# ---------------------------------------------------------------------------
# Helpers — mock batch result objects
# ---------------------------------------------------------------------------


def _make_result(custom_id: str, text: str, succeeded: bool = True):
    """Build a mock batch result object matching Anthropic's schema."""
    result = MagicMock()
    result.custom_id = custom_id

    if succeeded:
        result.result.type = "succeeded"
        result.result.message.content = [MagicMock(text=text)]
    else:
        result.result.type = "errored"
        result.result.error = "server_error"

    return result


def _valid_json(**overrides) -> str:
    """Return a valid enrichment JSON string."""
    data = {
        "tags": ["lakeside", "fishing"],
        "vibe": "Quiet lakeside retreat for families.",
        "elevator_pitch": "Peaceful lakeshore camping in old-growth forest.",
        "description_rewrite": "Set on the shore of a glacial lake, this campground offers swimming, fishing, and easy trail access.",
        "best_for": "families with young kids",
    }
    data.update(overrides)
    return json.dumps(data)


def _mock_registry(campground=None):
    """Build a mock CampgroundRegistry. Returns campground on lookup if provided."""
    reg = MagicMock()
    reg.get_by_facility_id.return_value = campground
    return reg


# ---------------------------------------------------------------------------
# Tests — successful enrichment
# ---------------------------------------------------------------------------


class TestProcessResultsSuccess:
    """Successful enrichment writes tags + descriptions to registry."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_recgov_enrichment(self, mock_anthropic_cls):
        cg = make_campground(id=1, facility_id="232465", booking_system=BookingSystem.RECGOV, tags=["forest"])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats == {"succeeded": 1, "errored": 0, "skipped": 0}
        registry.get_by_facility_id.assert_called_once_with("232465", booking_system=BookingSystem.RECGOV)
        registry.update_tags.assert_called_once()
        registry.update_vibe.assert_called_once_with(1, "Quiet lakeside retreat for families.")
        registry.update_description.assert_called_once()

    @patch("posthog.ai.anthropic.Anthropic")
    def test_tags_merged_with_existing(self, mock_anthropic_cls):
        """New tags are merged with existing, deduped."""
        cg = make_campground(id=1, tags=["forest", "lakeside"])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(tags=["lakeside", "fishing"])),
        ]

        process_results("fake-key", "batch_123", registry)

        # Merged: forest, lakeside (existing) + lakeside (dup removed), fishing (new)
        call_args = registry.update_tags.call_args[0]
        merged_tags = call_args[1]
        assert "forest" in merged_tags
        assert "lakeside" in merged_tags
        assert "fishing" in merged_tags
        assert len(merged_tags) == len(set(merged_tags))  # no dupes

    @patch("posthog.ai.anthropic.Anthropic")
    def test_multiple_results(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json()),
            _make_result("recgov_232465", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)
        assert stats["succeeded"] == 2


# ---------------------------------------------------------------------------
# Tests — custom_id parsing for different sources
# ---------------------------------------------------------------------------


class TestCustomIdParsing:
    """custom_id format: {source}_{facility_id} correctly maps to BookingSystem."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_wa_state_source(self, mock_anthropic_cls):
        cg = make_campground(id=2, facility_id="-2147483647", booking_system=BookingSystem.WA_STATE)
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("wa_state_-2147483647", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["succeeded"] == 1
        registry.get_by_facility_id.assert_called_once_with("-2147483647", booking_system=BookingSystem.WA_STATE)

    @patch("posthog.ai.anthropic.Anthropic")
    def test_or_state_source(self, mock_anthropic_cls):
        cg = make_campground(id=3, facility_id="409402", booking_system=BookingSystem.OR_STATE)
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("or_state_409402", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["succeeded"] == 1
        registry.get_by_facility_id.assert_called_once_with("409402", booking_system=BookingSystem.OR_STATE)

    @patch("posthog.ai.anthropic.Anthropic")
    def test_id_state_source(self, mock_anthropic_cls):
        cg = make_campground(id=4, facility_id="12345", booking_system=BookingSystem.ID_STATE)
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("id_state_12345", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["succeeded"] == 1
        registry.get_by_facility_id.assert_called_once_with("12345", booking_system=BookingSystem.ID_STATE)


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestProcessResultsErrors:
    """Error and edge cases increment the right counter."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_errored_result_type(self, mock_anthropic_cls):
        registry = _mock_registry()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", "", succeeded=False),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["errored"] == 1
        assert stats["succeeded"] == 0
        registry.get_by_facility_id.assert_not_called()

    @patch("posthog.ai.anthropic.Anthropic")
    def test_invalid_json_response(self, mock_anthropic_cls):
        registry = _mock_registry()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", "this is not json at all"),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["errored"] == 1
        assert stats["succeeded"] == 0

    @patch("posthog.ai.anthropic.Anthropic")
    def test_campground_not_found_skipped(self, mock_anthropic_cls):
        registry = _mock_registry(None)  # returns None for all lookups

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_999999", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats["skipped"] == 1
        assert stats["succeeded"] == 0

    @patch("posthog.ai.anthropic.Anthropic")
    def test_mixed_results(self, mock_anthropic_cls):
        """One succeeded, one errored, one skipped."""
        cg = make_campground(id=1)
        registry = MagicMock()
        # First call finds campground, second returns None (skipped)
        registry.get_by_facility_id.side_effect = [cg, None]

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json()),          # succeeded
            _make_result("recgov_111111", "", succeeded=False),    # errored
            _make_result("recgov_999999", _valid_json()),          # skipped (not found)
        ]

        stats = process_results("fake-key", "batch_123", registry)

        assert stats == {"succeeded": 1, "errored": 1, "skipped": 1}


# ---------------------------------------------------------------------------
# Tests — dry_run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry_run=True should not call any registry write methods."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_dry_run_no_writes(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json()),
        ]

        stats = process_results("fake-key", "batch_123", registry, dry_run=True)

        assert stats["succeeded"] == 1
        registry.update_tags.assert_not_called()
        registry.update_vibe.assert_not_called()
        registry.update_description.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — tag validation
# ---------------------------------------------------------------------------


class TestTagValidation:
    """Invalid tags filtered, renamed tags mapped correctly."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_invalid_tags_filtered(self, mock_anthropic_cls):
        cg = make_campground(id=1, tags=[])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(tags=["lakeside", "totally-fake", "swimming"])),
        ]

        process_results("fake-key", "batch_123", registry)

        call_args = registry.update_tags.call_args[0]
        written_tags = call_args[1]
        assert "totally-fake" not in written_tags
        assert "lakeside" in written_tags
        assert "swimming" in written_tags

    @patch("posthog.ai.anthropic.Anthropic")
    def test_renamed_tags_mapped(self, mock_anthropic_cls):
        """oceanfront -> beach, horse-camp -> equestrian."""
        cg = make_campground(id=1, tags=[])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(tags=["oceanfront", "horse-camp"])),
        ]

        process_results("fake-key", "batch_123", registry)

        call_args = registry.update_tags.call_args[0]
        written_tags = call_args[1]
        assert "beach" in written_tags
        assert "equestrian" in written_tags
        assert "oceanfront" not in written_tags
        assert "horse-camp" not in written_tags

    @patch("posthog.ai.anthropic.Anthropic")
    def test_removed_tags_dropped(self, mock_anthropic_cls):
        """scenic and glacier are dropped entirely."""
        cg = make_campground(id=1, tags=[])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(tags=["lakeside", "scenic", "glacier"])),
        ]

        process_results("fake-key", "batch_123", registry)

        call_args = registry.update_tags.call_args[0]
        written_tags = call_args[1]
        assert "scenic" not in written_tags
        assert "glacier" not in written_tags
        assert "lakeside" in written_tags

    @patch("posthog.ai.anthropic.Anthropic")
    def test_empty_tags_no_update(self, mock_anthropic_cls):
        """If all tags are invalid, update_tags is not called."""
        cg = make_campground(id=1, tags=[])
        registry = _mock_registry(cg)

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(tags=["scenic", "glacier"])),
        ]

        process_results("fake-key", "batch_123", registry)

        registry.update_tags.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — description truncation
# ---------------------------------------------------------------------------


class TestDescriptionTruncation:
    """Long descriptions are truncated to their field limits."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_long_vibe_truncated(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        long_vibe = "A" * 200  # well over 100 char limit

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(vibe=long_vibe)),
        ]

        process_results("fake-key", "batch_123", registry)

        vibe_written = registry.update_vibe.call_args[0][1]
        assert len(vibe_written) <= 100

    @patch("posthog.ai.anthropic.Anthropic")
    def test_long_elevator_pitch_truncated(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        long_pitch = "Word " * 50  # ~250 chars, over 120 limit

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(elevator_pitch=long_pitch)),
        ]

        process_results("fake-key", "batch_123", registry)

        pitch_written = registry.update_description.call_args[0][1]
        # _truncate may add "..." suffix, so allow small overshoot
        assert len(pitch_written) <= 125

    @patch("posthog.ai.anthropic.Anthropic")
    def test_long_description_rewrite_truncated(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        long_desc = "Word " * 100  # ~500 chars, over 350 limit

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(description_rewrite=long_desc)),
        ]

        process_results("fake-key", "batch_123", registry)

        desc_written = registry.update_description.call_args[0][2]
        assert len(desc_written) <= 355

    @patch("posthog.ai.anthropic.Anthropic")
    def test_long_best_for_truncated(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        long_best = "Word " * 20  # ~100 chars, over 50 limit

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", _valid_json(best_for=long_best)),
        ]

        process_results("fake-key", "batch_123", registry)

        best_written = registry.update_description.call_args[0][3]
        assert len(best_written) <= 55


# ---------------------------------------------------------------------------
# Tests — JSON parsing edge cases
# ---------------------------------------------------------------------------


class TestJsonParsing:
    """Markdown-fenced JSON and edge cases."""

    @patch("posthog.ai.anthropic.Anthropic")
    def test_markdown_fenced_json(self, mock_anthropic_cls):
        cg = make_campground(id=1)
        registry = _mock_registry(cg)

        fenced = "```json\n" + _valid_json() + "\n```"

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = [
            _make_result("recgov_232465", fenced),
        ]

        stats = process_results("fake-key", "batch_123", registry)
        assert stats["succeeded"] == 1

    @patch("posthog.ai.anthropic.Anthropic")
    def test_empty_batch(self, mock_anthropic_cls):
        registry = _mock_registry()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.batches.results.return_value = []

        stats = process_results("fake-key", "batch_123", registry)
        assert stats == {"succeeded": 0, "errored": 0, "skipped": 0}
