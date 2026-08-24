"""Tests for user-facing search warning copy.

Regression guard for a bug where every `waf_blocked` warning was hardcoded to
"WA State Parks results unavailable", so an Oregon outage told users Washington
was down. `source` was already threaded into the response and simply unused.
"""

from __future__ import annotations

import pytest

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.search import (
    SOURCE_LABELS,
    WARNING_TEMPLATES,
    warning_message,
)


@pytest.mark.parametrize(
    "source,expected_label",
    [
        ("or_state", "Oregon State Parks"),
        ("wa_state", "WA State Parks"),
        ("recgov", "Recreation.gov"),
        ("id_state", "Idaho State Parks"),
    ],
)
def test_warning_names_the_source_that_failed(source, expected_label):
    msg = warning_message("waf_blocked", source)
    assert expected_label in msg


def test_oregon_block_does_not_blame_washington():
    """The exact regression: an OR outage must not name WA."""
    msg = warning_message("waf_blocked", "or_state")
    assert "Oregon" in msg
    assert "WA State Parks" not in msg
    assert "Washington" not in msg


def test_washington_block_still_names_washington():
    assert "WA State Parks" in warning_message("waf_blocked", "wa_state")


@pytest.mark.parametrize("kind", sorted(WARNING_TEMPLATES))
def test_every_kind_renders_for_every_known_source(kind):
    for source in SOURCE_LABELS:
        msg = warning_message(kind, source)
        assert msg and "{" not in msg, (kind, source, msg)


def test_unknown_source_stays_vague_rather_than_guessing():
    """Better to say nothing specific than to name the wrong provider."""
    msg = warning_message("waf_blocked", "some_new_provider")
    assert "{" not in msg
    for label in SOURCE_LABELS.values():
        assert label not in msg


def test_unknown_kind_falls_back_cleanly():
    msg = warning_message("totally_new_kind", "or_state")
    assert msg == "Some campgrounds couldn't be checked."


def test_every_booking_system_has_a_label():
    """A new provider must not silently fall back to vague copy."""
    for system in BookingSystem:
        assert system.value in SOURCE_LABELS, system.value
