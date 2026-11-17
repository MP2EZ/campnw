"""Tests for LLM-enriched notification messages (notifications.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pnw_campsites.enrichment.notifications import enrich_notification


@pytest.fixture
def llm_reply(monkeypatch):
    """Patch the LLM client; `llm_reply(text)` or `llm_reply(error=exc)` returns the mock client."""

    def _install(text: str | None = None, error: Exception | None = None) -> AsyncMock:
        client = AsyncMock()
        if error is not None:
            client.messages.create = AsyncMock(side_effect=error)
        else:
            response = MagicMock()
            response.content = [MagicMock(text=text)]
            client.messages.create = AsyncMock(return_value=response)
        monkeypatch.setattr("pnw_campsites.posthog_client.get_anthropic_client", lambda api_key: client)
        return client

    return _install


async def _enrich(name="Test Camp", site_count=1, dates=("2026-06-10",)):
    return await enrich_notification(
        campground_name=name, site_count=site_count, dates=list(dates), api_key="test-key",
    )


def _prompt(client: AsyncMock) -> str:
    return client.messages.create.call_args.kwargs["messages"][0]["content"]


class TestEnrichNotification:
    """Test the enrich_notification async function."""

    async def test_valid_response(self, llm_reply):
        llm_reply('{"message": "Popular weekend spot just opened!"}')

        message = await _enrich("Lake Sammamish", 3, ["2026-06-13", "2026-06-14"])

        assert message == "Popular weekend spot just opened!"

    async def test_no_api_key_returns_fallback(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        message = await enrich_notification(
            campground_name="Lake Camp", site_count=2, dates=["2026-06-15"], api_key="",
        )

        assert message == "2 sites open at Lake Camp"

    async def test_api_error_returns_fallback(self, llm_reply):
        llm_reply(error=RuntimeError("API Error"))

        assert await _enrich("River Camp", 1, ["2026-07-01"]) == "1 site open at River Camp"

    async def test_invalid_json_returns_fallback(self, llm_reply):
        llm_reply("not valid json")

        assert await _enrich("Test Camp", 5, ["2026-06-20"]) == "5 sites open at Test Camp"

    async def test_json_in_markdown_block(self, llm_reply):
        llm_reply('```json\n{"message": "Peak weekend availability!"}\n```')

        assert await _enrich("Popular Park", 4) == "Peak weekend availability!"

    async def test_missing_message_returns_fallback(self, llm_reply):
        llm_reply('{"other": 2}')

        assert await _enrich() == "1 site open at Test Camp"

    async def test_date_formatting_in_prompt(self, llm_reply):
        client = llm_reply('{"message": "Sites available"}')

        message = await _enrich(site_count=5, dates=[f"2026-06-{d:02d}" for d in range(10, 15)])

        prompt = _prompt(client)
        assert "2026-06-10" in prompt
        assert "2026-06-14" in prompt
        assert message == "Sites available"

    async def test_prompt_includes_brand_voice_rules(self, llm_reply):
        client = llm_reply('{"message": "Test"}')

        await _enrich("Test")

        prompt = _prompt(client)
        assert "No emoji" in prompt
        assert "exclamation marks" in prompt.lower()
        assert "snag" in prompt
        assert "grab" in prompt
        assert "Declarative" in prompt

    async def test_many_dates_truncated(self, llm_reply):
        client = llm_reply('{"message": "Many dates open"}')

        message = await _enrich("Busy Camp", 10, [f"2026-06-{d:02d}" for d in range(1, 21)])

        assert "(+6 more)" in _prompt(client)
        assert message == "Many dates open"
