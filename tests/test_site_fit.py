"""Site fit decoding: WA equipment ids, WA loop descriptions, Recreation.gov
campsite types → SiteFit. None means unknown."""

import pytest

from pnw_campsites.registry.models import SiteFit
from pnw_campsites.search.site_fit import (
    fit_from_recgov_type,
    fit_from_wa_equipment,
    parse_loop_site_types,
    wa_site_fit,
)


def _equip(*sub_ids: int) -> list[dict]:
    """allowed_equipment as stored in wa_state_sites."""
    return [{"equipmentCategoryId": -32768, "subEquipmentCategoryId": s} for s in sub_ids]


# Real Fort Ebey (-2147483616) rows from wa_state_sites, 2026-11-07.
FORT_EBEY_7 = _equip(-32768, -32767, -32766, -32765, -32764, -32763, -32759)
FORT_EBEY_9 = _equip(-32768)
FORT_EBEY_20 = _equip(-32768, -32767, -32766, -32765, -32764, -32763, -32762, -32759, -32758)
FORT_EBEY_MAIN = (
    "Sites 1-53, HB1 & HB2 (Serviced = 1-4, 21-30) (Standard = 5-20, 31-50) "
    "(Walkin = 51-53) (Hiker-Biker = HB1 & HB2)"
)


class TestWaEquipment:
    def test_tent_van_rv_up_to_30(self) -> None:
        fit = fit_from_wa_equipment(FORT_EBEY_7)
        assert (fit.fits_tent, fit.fits_van, fit.fits_rv, fit.max_rv_ft) == (True, True, True, 30)

    def test_tent_only(self) -> None:
        fit = fit_from_wa_equipment(FORT_EBEY_9)
        assert (fit.fits_tent, fit.fits_van, fit.fits_rv, fit.max_rv_ft) == (True, False, False, None)

    def test_band_ids_are_not_ordered_by_length(self) -> None:
        # -32762 is 35' and -32759 is 30'; the longest band wins, not the lowest id.
        assert fit_from_wa_equipment(FORT_EBEY_20).max_rv_ft == 40
        assert fit_from_wa_equipment(_equip(-32764, -32762)).max_rv_ft == 35

    def test_over_40_has_no_upper_limit(self) -> None:
        # Real over-40 sites always list the bounded bands too; -32757 still wins.
        fit = fit_from_wa_equipment(_equip(-32764, -32758, -32757))
        assert (fit.fits_rv, fit.max_rv_ft) == (True, None)
        assert fit_from_wa_equipment(_equip(-32757)).fits_van is False

    def test_rv_without_tent(self) -> None:
        fit = fit_from_wa_equipment(_equip(-32765, -32764, -32763))
        assert (fit.fits_tent, fit.fits_van, fit.fits_rv, fit.max_rv_ft) == (False, True, True, 25)

    def test_group_trailers_fit_rvs_of_unstated_length(self) -> None:
        fit = fit_from_wa_equipment(
            [{"equipmentCategoryId": -32767, "subEquipmentCategoryId": -32760}]
        )
        assert (fit.fits_rv, fit.max_rv_ft) == (True, None)

    @pytest.mark.parametrize("allowed", [[], None, _equip(-1), [{"bad": 1}]])
    def test_empty_or_unrecognised_is_unknown(self, allowed) -> None:
        assert fit_from_wa_equipment(allowed) == SiteFit()

    def test_hookups_and_walk_in_are_not_from_equipment(self) -> None:
        fit = fit_from_wa_equipment(FORT_EBEY_7)
        assert (fit.hookups, fit.walk_in) == (None, None)


class TestParseLoopSiteTypes:
    def test_fort_ebey_main(self) -> None:
        types = parse_loop_site_types(FORT_EBEY_MAIN)
        assert types["7"] == (False, False)  # standard
        assert types["27"] == (True, False)  # serviced
        assert types["52"] == (False, True)  # walk-in
        assert types["HB1"] == (False, True)  # hiker-biker
        # The overview range "1-53" is not a label.
        assert "54" not in types

    def test_label_after_ranges(self) -> None:
        types = parse_loop_site_types(
            "1-2, 5-65, 68, 70-78 (Serviced) 3-4, 66-67, 69 (Standard)"
        )
        assert types["1"] == (True, False)
        assert types["66"] == (False, False)

    def test_label_inside_parens_after_ranges(self) -> None:
        types = parse_loop_site_types(
            "Sites 1-18 (Sites 1-8 Serviced, 9-18 Standard, HB1-HB2 Hiker/Biker)"
        )
        assert types["8"] == (True, False)
        assert types["9"] == (False, False)
        assert types["HB2"] == (False, True)

    def test_prefix_label_ends_at_close_paren(self) -> None:
        types = parse_loop_site_types(
            "Sites 79-145 (Serviced = 81-87, 89-91 Standard = 79-80, 88, 92-145), "
            "226-230 (Serviced = 226 Standard = 227-230)"
        )
        assert types["81"] == (True, False)
        assert types["88"] == (False, False)
        assert types["226"] == (True, False)
        assert types["230"] == (False, False)

    def test_unpunctuated_labels_and_to_ranges(self) -> None:
        types = parse_loop_site_types("Sites 1-25 Serviced, 27-47 Unserviced")
        assert types["25"] == (True, False)
        assert types["27"] == (False, False)
        assert parse_loop_site_types("Sites 29 to 45 (Primitive)")["30"] == (False, None)

    def test_conflicting_labels_become_unknown(self) -> None:
        # Real Birch Bay A: 125 is listed as both standard and serviced.
        types = parse_loop_site_types("Sites 75-130 (All Standard), 125 (Serviced)")
        assert types["124"] == (False, False)
        assert types["125"] == (None, False)

    def test_cabins_and_shelters_carry_no_site_type(self) -> None:
        types = parse_loop_site_types("Sites 2-29 (Serviced), C1-C2 (Roofed)")
        assert types["C1"] == (None, None)

    def test_leading_zeros_and_letter_suffixes_normalise(self) -> None:
        assert parse_loop_site_types("Sites 56D-60D (Serviced)")["57D"] == (True, False)
        assert parse_loop_site_types("Sites 01-03 (Standard)")["2"] == (False, False)

    @pytest.mark.parametrize(
        "description", ["", "Fort Ebey Overview Map", "Sites 1-46, G2", "Sites 1-34 and Group Camp"],
    )
    def test_unlabelled_descriptions_give_nothing(self, description) -> None:
        assert {k: v for k, v in parse_loop_site_types(description).items() if v != (None, None)} == {}


class TestWaSiteFit:
    @pytest.mark.parametrize(
        ("name", "equipment", "expected"),
        [
            ("7", FORT_EBEY_7, SiteFit(fits_tent=True, fits_van=True, fits_rv=True, max_rv_ft=30, hookups=False, walk_in=False)),
            ("9", FORT_EBEY_9, SiteFit(fits_tent=True, fits_van=False, fits_rv=False, hookups=False, walk_in=False)),
            ("27", FORT_EBEY_7, SiteFit(fits_tent=True, fits_van=True, fits_rv=True, max_rv_ft=30, hookups=True, walk_in=False)),
        ],
    )
    def test_fort_ebey_sites(self, name, equipment, expected) -> None:
        assert wa_site_fit(name, equipment, FORT_EBEY_MAIN) == expected

    def test_site_missing_from_description_keeps_equipment_fit(self) -> None:
        fit = wa_site_fit("99", FORT_EBEY_9, FORT_EBEY_MAIN)
        assert (fit.fits_tent, fit.hookups, fit.walk_in) == (True, None, None)

    def test_no_metadata_is_unknown(self) -> None:
        assert wa_site_fit("7", [], "") == SiteFit()


class TestRecgovType:
    @pytest.mark.parametrize(
        ("campsite_type", "expected"),
        [
            ("TENT ONLY NONELECTRIC", SiteFit(fits_tent=True, fits_van=False, fits_rv=False, hookups=False)),
            ("RV ELECTRIC", SiteFit(fits_van=True, fits_rv=True, hookups=True, walk_in=False)),
            ("STANDARD NONELECTRIC", SiteFit(hookups=False, walk_in=False)),
            ("STANDARD ELECTRIC", SiteFit(hookups=True, walk_in=False)),
            ("WALK TO", SiteFit(fits_tent=True, fits_van=False, fits_rv=False, walk_in=True)),
            ("HIKE TO", SiteFit(fits_tent=True, fits_van=False, fits_rv=False, walk_in=True)),
            ("GROUP TENT ONLY AREA NONELECTRIC", SiteFit(fits_tent=True, fits_van=False, fits_rv=False, hookups=False)),
            ("CABIN ELECTRIC", SiteFit(fits_tent=False, fits_van=False, fits_rv=False, hookups=True)),
            ("YURT", SiteFit(fits_tent=False, fits_van=False, fits_rv=False)),
            ("EQUESTRIAN NONELECTRIC", SiteFit(hookups=False)),
            ("MANAGEMENT", SiteFit()),
            ("", SiteFit()),
        ],
    )
    def test_types(self, campsite_type, expected) -> None:
        assert fit_from_recgov_type(campsite_type) == expected

    def test_never_invents_rv_length(self) -> None:
        assert fit_from_recgov_type("RV NONELECTRIC").max_rv_ft is None
