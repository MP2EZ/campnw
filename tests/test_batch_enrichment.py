"""Tests for batch enrichment: request building, JSON parsing."""

from __future__ import annotations

from pnw_campsites.enrichment.batch import build_batch_requests
from pnw_campsites.enrichment.llm_tags import parse_llm_json
from tests.conftest import make_campground

# ---------------------------------------------------------------------------
# parse_llm_json
# ---------------------------------------------------------------------------


class TestParseLlmJson:
    def test_plain_json(self):
        result = parse_llm_json('{"tags": ["lakeside"], "vibe": "Nice"}')
        assert result == {"tags": ["lakeside"], "vibe": "Nice"}

    def test_markdown_fenced_json(self):
        text = '```json\n{"tags": ["forest"]}\n```'
        result = parse_llm_json(text)
        assert result == {"tags": ["forest"]}

    def test_markdown_no_language(self):
        text = '```\n{"tags": []}\n```'
        result = parse_llm_json(text)
        assert result == {"tags": []}

    def test_fence_after_preamble(self):
        text = 'Here you go:\n```json\n{"tags": ["forest"]}\n```'
        assert parse_llm_json(text) == {"tags": ["forest"]}

    def test_backticks_inside_plain_json(self):
        assert parse_llm_json('{"vibe": "a ``` b"}') == {"vibe": "a ``` b"}

    def test_invalid_json_returns_none(self):
        assert parse_llm_json("not json at all") is None

    def test_empty_string_returns_none(self):
        assert parse_llm_json("") is None

    def test_whitespace_wrapped(self):
        result = parse_llm_json('  \n {"tags": []}  \n ')
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
