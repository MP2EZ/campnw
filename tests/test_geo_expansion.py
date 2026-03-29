"""Tests for registry expansion — new known bases and bounding box."""

from __future__ import annotations

from pnw_campsites.geo import KNOWN_BASES, is_known_base, resolve_base

import pytest


class TestNewKnownBases:
    """Tests for the expanded known bases list."""

    def test_original_bases_preserved(self):
        for base in ("seattle", "bellevue", "portland",
                      "spokane", "bellingham", "moscow"):
            assert base in KNOWN_BASES

    def test_new_bases_added(self):
        for base in ("bozeman", "missoula", "jackson",
                      "sacramento", "reno", "bend"):
            assert base in KNOWN_BASES

    def test_all_bases_have_valid_coords(self):
        for name, (lat, lon) in KNOWN_BASES.items():
            assert 30.0 < lat < 50.0, f"{name} lat {lat} out of range"
            assert -130.0 < lon < -100.0, f"{name} lon {lon} out of range"

    def test_is_known_base_new_entries(self):
        assert is_known_base("bozeman")
        assert is_known_base("Bozeman")  # case insensitive
        assert is_known_base("JACKSON")
        assert is_known_base("reno")

    def test_resolve_base_new_entries(self):
        lat, lon = resolve_base("bozeman")
        assert 45.0 < lat < 46.5
        assert -112.0 < lon < -110.0

    def test_resolve_base_case_insensitive(self):
        assert resolve_base("Sacramento") == resolve_base("sacramento")

    def test_resolve_base_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown base"):
            resolve_base("timbuktu")

    def test_bend_coordinates(self):
        """Bend, OR should be in central Oregon."""
        lat, lon = KNOWN_BASES["bend"]
        assert 43.5 < lat < 44.5
        assert -122.0 < lon < -121.0

    def test_jackson_coordinates(self):
        """Jackson, WY should be near Grand Teton."""
        lat, lon = KNOWN_BASES["jackson"]
        assert 43.0 < lat < 44.0
        assert -111.5 < lon < -110.0
