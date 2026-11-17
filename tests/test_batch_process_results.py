"""Tests for batch.process_results() — enrichment result processing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

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


def _run(results, registry, **kw):
    """Run process_results against a patched Anthropic client returning `results`."""
    with patch("posthog.ai.anthropic.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.batches.results.return_value = results
        return process_results("fake-key", "batch_123", registry, **kw)


def _one(registry, text=None, custom_id="recgov_232465", **kw):
    return _run([_make_result(custom_id, text if text is not None else _valid_json())], registry, **kw)


class TestProcessResultsSuccess:
    """Successful enrichment writes tags + descriptions to registry."""

    def test_recgov_enrichment(self):
        cg = make_campground(id=1, facility_id="232465", booking_system=BookingSystem.RECGOV, tags=["forest"])
        registry = _mock_registry(cg)

        stats = _one(registry)

        assert stats == {"succeeded": 1, "errored": 0, "skipped": 0}
        registry.get_by_facility_id.assert_called_once_with("232465", booking_system=BookingSystem.RECGOV)
        registry.update_tags.assert_called_once()
        registry.update_vibe.assert_called_once_with(1, "Quiet lakeside retreat for families.")
        registry.update_description.assert_called_once()

    def test_tags_merged_with_existing(self):
        """New tags are merged with existing, deduped."""
        registry = _mock_registry(make_campground(id=1, tags=["forest", "lakeside"]))

        _one(registry, _valid_json(tags=["lakeside", "fishing"]))

        merged_tags = registry.update_tags.call_args[0][1]
        assert "forest" in merged_tags
        assert "lakeside" in merged_tags
        assert "fishing" in merged_tags
        assert len(merged_tags) == len(set(merged_tags))

    def test_multiple_results(self):
        registry = _mock_registry(make_campground(id=1))

        stats = _run([_make_result("recgov_232465", _valid_json())] * 2, registry)

        assert stats["succeeded"] == 2


class TestCustomIdParsing:
    """custom_id format: {source}_{facility_id} correctly maps to BookingSystem."""

    @pytest.mark.parametrize(
        ("custom_id", "facility_id", "system"),
        [
            ("wa_state_-2147483647", "-2147483647", BookingSystem.WA_STATE),
            ("or_state_409402", "409402", BookingSystem.OR_STATE),
            ("id_state_12345", "12345", BookingSystem.ID_STATE),
        ],
    )
    def test_state_sources(self, custom_id, facility_id, system):
        registry = _mock_registry(make_campground(id=2, facility_id=facility_id, booking_system=system))

        stats = _one(registry, custom_id=custom_id)

        assert stats["succeeded"] == 1
        registry.get_by_facility_id.assert_called_once_with(facility_id, booking_system=system)


class TestProcessResultsErrors:
    """Error and edge cases increment the right counter."""

    def test_errored_result_type(self):
        registry = _mock_registry()

        stats = _run([_make_result("recgov_232465", "", succeeded=False)], registry)

        assert stats["errored"] == 1
        assert stats["succeeded"] == 0
        registry.get_by_facility_id.assert_not_called()

    def test_invalid_json_response(self):
        stats = _one(_mock_registry(), "this is not json at all")

        assert stats["errored"] == 1
        assert stats["succeeded"] == 0

    def test_campground_not_found_skipped(self):
        stats = _one(_mock_registry(None), custom_id="recgov_999999")

        assert stats["skipped"] == 1
        assert stats["succeeded"] == 0

    def test_mixed_results(self):
        """One succeeded, one errored, one skipped."""
        registry = MagicMock()
        registry.get_by_facility_id.side_effect = [make_campground(id=1), None]

        stats = _run(
            [
                _make_result("recgov_232465", _valid_json()),  # succeeded
                _make_result("recgov_111111", "", succeeded=False),  # errored
                _make_result("recgov_999999", _valid_json()),  # skipped (not found)
            ],
            registry,
        )

        assert stats == {"succeeded": 1, "errored": 1, "skipped": 1}


class TestDryRun:
    """dry_run=True should not call any registry write methods."""

    def test_dry_run_no_writes(self):
        registry = _mock_registry(make_campground(id=1))

        stats = _one(registry, dry_run=True)

        assert stats["succeeded"] == 1
        registry.update_tags.assert_not_called()
        registry.update_vibe.assert_not_called()
        registry.update_description.assert_not_called()


class TestTagValidation:
    """Invalid tags filtered, renamed tags mapped correctly."""

    def test_invalid_tags_filtered(self):
        registry = _mock_registry(make_campground(id=1, tags=[]))

        _one(registry, _valid_json(tags=["lakeside", "totally-fake", "swimming"]))

        written_tags = registry.update_tags.call_args[0][1]
        assert "totally-fake" not in written_tags
        assert "lakeside" in written_tags
        assert "swimming" in written_tags

    def test_renamed_tags_mapped(self):
        """oceanfront -> beach, horse-camp -> equestrian."""
        registry = _mock_registry(make_campground(id=1, tags=[]))

        _one(registry, _valid_json(tags=["oceanfront", "horse-camp"]))

        written_tags = registry.update_tags.call_args[0][1]
        assert "beach" in written_tags
        assert "equestrian" in written_tags
        assert "oceanfront" not in written_tags
        assert "horse-camp" not in written_tags

    def test_removed_tags_dropped(self):
        """scenic and glacier are dropped entirely."""
        registry = _mock_registry(make_campground(id=1, tags=[]))

        _one(registry, _valid_json(tags=["lakeside", "scenic", "glacier"]))

        written_tags = registry.update_tags.call_args[0][1]
        assert "scenic" not in written_tags
        assert "glacier" not in written_tags
        assert "lakeside" in written_tags

    def test_empty_tags_no_update(self):
        """If all tags are invalid, update_tags is not called."""
        registry = _mock_registry(make_campground(id=1, tags=[]))

        _one(registry, _valid_json(tags=["scenic", "glacier"]))

        registry.update_tags.assert_not_called()


class TestDescriptionTruncation:
    """Long descriptions are truncated to their field limits."""

    @pytest.mark.parametrize(
        ("field", "text", "write_call", "arg_index", "max_len"),
        [
            ("vibe", "A" * 200, "update_vibe", 1, 100),
            ("elevator_pitch", "Word " * 50, "update_description", 1, 125),  # _truncate may add "..."
            ("description_rewrite", "Word " * 100, "update_description", 2, 355),
            ("best_for", "Word " * 20, "update_description", 3, 55),
        ],
    )
    def test_long_field_truncated(self, field, text, write_call, arg_index, max_len):
        registry = _mock_registry(make_campground(id=1))

        _one(registry, _valid_json(**{field: text}))

        written = getattr(registry, write_call).call_args[0][arg_index]
        assert len(written) <= max_len


class TestJsonParsing:
    """Markdown-fenced JSON and edge cases."""

    def test_markdown_fenced_json(self):
        registry = _mock_registry(make_campground(id=1))

        stats = _one(registry, "```json\n" + _valid_json() + "\n```")

        assert stats["succeeded"] == 1

    def test_empty_batch(self):
        stats = _run([], _mock_registry())

        assert stats == {"succeeded": 0, "errored": 0, "skipped": 0}
