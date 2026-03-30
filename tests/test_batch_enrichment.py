"""Tests for batch enrichment: truncation scoring, request building, JSON parsing."""

from __future__ import annotations

import json

import pytest

from pnw_campsites.enrichment.batch import (
    _parse_json_response,
    build_batch_requests,
    campground_truncation_score,
    truncation_score,
)
from tests.conftest import make_campground


# ---------------------------------------------------------------------------
# truncation_score
# ---------------------------------------------------------------------------


class TestTruncationScore:
    def test_clean_sentence_scores_zero(self):
        assert truncation_score("Perfect for families.", "best_for") == 0.0

    def test_empty_string_scores_zero(self):
        assert truncation_score("", "elevator_pitch") == 0.0

    def test_exact_old_limit_high_score(self):
        """Text hitting the old 100-char limit exactly should score high."""
        text = "A" * 100
        score = truncation_score(text, "elevator_pitch")
        assert score >= 0.8  # old limit (0.5) + mid-word (0.3)

    def test_exact_old_limit_250(self):
        text = "B" * 250
        score = truncation_score(text, "description_rewrite")
        assert score >= 0.8

    def test_exact_old_limit_30(self):
        text = "C" * 30
        score = truncation_score(text, "best_for")
        assert score >= 0.8

    def test_ellipsis_ending(self):
        score = truncation_score("Beautiful lakeside camping...", "vibe")
        assert score >= 0.4

    def test_mid_word_cut(self):
        """Ending mid-word without punctuation should score."""
        score = truncation_score("Perfect for families and pet", "best_for")
        assert score >= 0.3

    def test_complete_sentence_low_score(self):
        """A properly ended sentence should score very low (only short-length signal)."""
        score = truncation_score("Shaded riverside camping with old-growth trees and river access.", "elevator_pitch")
        assert score == 0.0

    def test_question_mark_ending_low_score(self):
        score = truncation_score("Ready for an adventure along the riverside trails and lakeside views?", "elevator_pitch")
        assert score == 0.0

    def test_quote_ending_low_score(self):
        score = truncation_score('This campground is locally known as "the quiet camp"', "vibe")
        assert score == 0.0

    def test_suspiciously_short(self):
        """Very short text for a field that expects more."""
        score = truncation_score("camp", "description_rewrite")
        assert score > 0.0

    def test_score_capped_at_one(self):
        """Multiple signals shouldn't exceed 1.0."""
        # Hits old limit + mid-word + no punctuation
        text = "A" * 100
        score = truncation_score(text, "elevator_pitch")
        assert score <= 1.0


# ---------------------------------------------------------------------------
# campground_truncation_score
# ---------------------------------------------------------------------------


class TestCampgroundTruncationScore:
    def test_no_fields_scores_zero(self):
        cg = make_campground(elevator_pitch="", description_rewrite="", best_for="", vibe="")
        assert campground_truncation_score(cg) == 0.0

    def test_one_truncated_field(self):
        cg = make_campground(
            elevator_pitch="A" * 100,  # hits old limit
            description_rewrite="Clean sentence here.",
            best_for="families",
        )
        assert campground_truncation_score(cg) >= 0.8

    def test_all_clean_fields(self):
        cg = make_campground(
            elevator_pitch="Beautiful lakeside camping for families with river access and trails.",
            description_rewrite="Nestled along the river with towering old-growth trees surrounding the campground. Perfect for weekend getaways.",
            best_for="Families with young kids and pets.",
            vibe="Quiet riverside camping under towering Douglas fir and cedar trees.",
        )
        assert campground_truncation_score(cg) == 0.0

    def test_returns_max_of_fields(self):
        """Should return the highest score among all fields."""
        cg = make_campground(
            elevator_pitch="Clean sentence.",  # 0.0
            best_for="A" * 30,  # hits old limit → high
        )
        score = campground_truncation_score(cg)
        assert score >= 0.5


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_plain_json(self):
        result = _parse_json_response('{"tags": ["lakeside"], "vibe": "Nice"}')
        assert result == {"tags": ["lakeside"], "vibe": "Nice"}

    def test_markdown_fenced_json(self):
        text = '```json\n{"tags": ["forest"]}\n```'
        result = _parse_json_response(text)
        assert result == {"tags": ["forest"]}

    def test_markdown_no_language(self):
        text = '```\n{"tags": []}\n```'
        result = _parse_json_response(text)
        assert result == {"tags": []}

    def test_invalid_json_returns_none(self):
        assert _parse_json_response("not json at all") is None

    def test_empty_string_returns_none(self):
        assert _parse_json_response("") is None

    def test_whitespace_wrapped(self):
        result = _parse_json_response('  \n {"tags": []}  \n ')
        assert result == {"tags": []}


# ---------------------------------------------------------------------------
# build_batch_requests
# ---------------------------------------------------------------------------


class TestBuildBatchRequests:
    def test_builds_correct_structure(self):
        cg = make_campground(facility_id="232465", name="Ohanapecosh")
        requests = build_batch_requests([cg])
        assert len(requests) == 1
        req = requests[0]
        assert req["custom_id"] == "recgov_232465"
        assert req["params"]["model"] == "claude-haiku-4-5-20251001"
        assert req["params"]["max_tokens"] == 500
        assert len(req["params"]["messages"]) == 1
        assert "Ohanapecosh" in req["params"]["messages"][0]["content"]

    def test_custom_id_format_valid(self):
        """Custom IDs must match ^[a-zA-Z0-9_-]{1,64}$"""
        import re
        pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

        cgs = [
            make_campground(facility_id="232465"),
            make_campground(facility_id="-2147483624"),  # WA State negative ID
            make_campground(facility_id="10283829"),
        ]
        requests = build_batch_requests(cgs)
        for req in requests:
            assert pattern.match(req["custom_id"]), f"Invalid custom_id: {req['custom_id']}"

    def test_multiple_campgrounds(self):
        cgs = [make_campground(facility_id=str(i)) for i in range(5)]
        requests = build_batch_requests(cgs)
        assert len(requests) == 5
        ids = {r["custom_id"] for r in requests}
        assert len(ids) == 5  # all unique
