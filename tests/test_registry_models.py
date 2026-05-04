"""Tests for registry data models."""

from __future__ import annotations

import pytest

from pnw_campsites.registry.models import BookingSystem


class TestBookingSystemEnum:
    """BookingSystem accepts canonical underscore-style + dash-style aliases."""

    def test_canonical_underscore_values(self) -> None:
        """The canonical wa_state/or_state/etc. values still work."""
        assert BookingSystem("recgov") is BookingSystem.RECGOV
        assert BookingSystem("wa_state") is BookingSystem.WA_STATE
        assert BookingSystem("or_state") is BookingSystem.OR_STATE
        assert BookingSystem("id_state") is BookingSystem.ID_STATE
        assert BookingSystem("fcfs") is BookingSystem.FCFS

    def test_dash_aliases_resolve_to_canonical(self) -> None:
        """Dash-style values from CLI/URLs resolve to the underscore enum."""
        assert BookingSystem("wa-state") is BookingSystem.WA_STATE
        assert BookingSystem("or-state") is BookingSystem.OR_STATE
        assert BookingSystem("id-state") is BookingSystem.ID_STATE

    def test_unknown_value_still_raises(self) -> None:
        """Unrecognized strings still raise ValueError (no accidental rescue)."""
        with pytest.raises(ValueError):
            BookingSystem("nonsense")

    def test_dash_to_underscore_does_not_rescue_gibberish(self) -> None:
        """Dash-replacement only rescues actual enum values, not arbitrary strings."""
        with pytest.raises(ValueError):
            BookingSystem("not-a-thing")
        with pytest.raises(ValueError):
            BookingSystem("rec-gov")  # 'rec_gov' is also not an enum value

    def test_str_enum_values_still_strings(self) -> None:
        """BookingSystem is a StrEnum; values compare equal to their string form."""
        assert BookingSystem.WA_STATE == "wa_state"
        assert BookingSystem("wa-state") == "wa_state"
