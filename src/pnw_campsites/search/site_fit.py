"""Decode what each booking system says a site takes into a SiteFit.

Pure functions. Anything a source doesn't state stays None (unknown), never
False: a park with no site metadata must not read as "doesn't fit".
"""

from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache

from pnw_campsites.registry.models import SiteFit

# ---------------------------------------------------------------------------
# WA State Parks (GoingToCamp)
# ---------------------------------------------------------------------------

# GoingToCamp /api/equipment sub-equipment ids, verified against a live fetch
# on 2026-11-07. Stored here because prod can't reach GoingToCamp.
_WA_TENTS = {-32768, -32767, -32766, -32761}  # 1-3 tents; group tents
_WA_VAN = -32765  # 1 Van/Camper
_WA_GROUP_TRAILERS = -32760  # no length band
# RV/Trailer bands. Ids aren't in length order. "Over 40'" (-32757) states no
# upper limit, so it reports 40, the longest length GoingToCamp states.
_WA_RV_BANDS_FT = {
    -32764: 20, -32763: 25, -32759: 30, -32762: 35, -32758: 40, -32757: 40,
}
_WA_KNOWN = _WA_TENTS | {_WA_VAN, _WA_GROUP_TRAILERS} | set(_WA_RV_BANDS_FT)


def fit_from_wa_equipment(allowed: list[dict] | None) -> SiteFit:
    """Tent / van / RV fit from wa_state_sites.allowed_equipment."""
    ids = {
        e.get("subEquipmentCategoryId") for e in allowed or [] if isinstance(e, dict)
    }
    if not ids & _WA_KNOWN:
        return SiteFit()
    lengths = [_WA_RV_BANDS_FT[i] for i in ids if i in _WA_RV_BANDS_FT]
    return SiteFit(
        fits_tent=bool(ids & _WA_TENTS),
        fits_van=_WA_VAN in ids,
        fits_rv=bool(lengths) or _WA_GROUP_TRAILERS in ids,
        max_rv_ft=max(lengths) if lengths else None,
    )


# Loop descriptions name site types by number, in two shapes:
#   "Sites 1-4, 21-30 (Serviced)"          ranges, then their label
#   "(Serviced = 1-4, 21-30)"              label, "=", then its ranges
_SITE = r"([A-Z]*)(\d+)([A-Z]*)"
_TOKEN_RE = re.compile(
    rf"""
    (?P<range>\b{_SITE}\s*(?:-|–|\bto\b)\s*{_SITE}\b)
    |(?P<site>\b[A-Z]*\d+[A-Z]*\b)
    |(?P<label>walk[\s-]?ins?|hiker[\s/-]*bikers?|unserviced|non[\s-]?serviced
       |serviced|electric|(?:full|partial)\s+hook-?ups?|standard|primitive
       |cabins?|yurts?|roofed|shelters?|te{{1,2}}pees?|vacation\s+houses?
       |slips?|group|overflow|marine\s+trail)
    |(?P<eq>=)|(?P<open>\()|(?P<close>\))
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NAME_RE = re.compile(rf"^{_SITE}$")
_MAX_RANGE = 500

# label → (hookups, walk_in). Cabins, shelters etc. aren't campsite types.
_NOT_A_SITE_TYPE = (None, None)


def _label_features(label: str) -> tuple[bool | None, bool | None]:
    word = label.lower()
    if word.startswith(("unserviced", "non", "standard")):
        return (False, False)
    if word.startswith(("serviced", "electric", "full", "partial")):
        return (True, False)
    if word.startswith("primitive"):
        return (False, None)
    if word.startswith(("walk", "hiker")):
        return (False, True)
    return _NOT_A_SITE_TYPE


def _site_key(prefix: str, number: int, suffix: str) -> str:
    return f"{prefix.upper()}{number}{suffix.upper()}"


def _site_names(m: re.Match) -> list[str]:
    if not m["range"]:
        return [normalize_site_name(m["site"]) or m["site"].upper()]
    p1, n1, s1, p2, n2, s2 = m.groups()[1:7]
    lo, hi = int(n1), int(n2)
    if (p2 or p1).upper() == p1.upper() and (s2 or s1).upper() == s1.upper() \
            and 0 <= hi - lo <= _MAX_RANGE:
        return [_site_key(p1, n, s1) for n in range(lo, hi + 1)]
    return [_site_key(p1, lo, s1), _site_key(p2, hi, s2)]


def normalize_site_name(name: str) -> str | None:
    """'007' → '7', 'hb1' → 'HB1'. None for names that aren't a number."""
    m = _NAME_RE.match(name.strip().upper())
    return _site_key(m[1], int(m[2]), m[3]) if m else None


@lru_cache(maxsize=512)
def parse_loop_site_types(
    description: str,
) -> dict[str, tuple[bool | None, bool | None]]:
    """Site name → (hookups, walk_in) from a wa_state_loops description.

    Tolerant: unlabelled ranges give nothing, and a site given two labels
    keeps only the fields they agree on. Cached per description (one parse
    per loop, not per site), so callers must not mutate the result.
    """
    seen: dict[str, set[tuple[bool | None, bool | None]]] = defaultdict(set)
    tokens = list(_TOKEN_RE.finditer(description or ""))
    pending: list[str] = []  # sites waiting for a label after them
    outer: list[str] = []  # pending from before an open paren
    prefix: tuple[bool | None, bool | None] | None = None  # "Label = ..."

    def assign(names: list[str], features: tuple[bool | None, bool | None]) -> None:
        for name in names:
            seen[name].add(features)

    for i, m in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if m["range"] or m["site"]:
            if prefix is not None:
                assign(_site_names(m), prefix)
            else:
                pending.extend(_site_names(m))
        elif m["label"]:
            features = _label_features(m["label"])
            if nxt is not None and nxt["eq"]:
                prefix, pending, outer = features, [], []
            elif pending:
                assign(pending, features)
                pending, prefix = [], None
            elif outer:
                assign(outer, features)
                outer, prefix = [], None
        elif m["open"]:
            outer, pending, prefix = pending, [], None
        elif m["close"]:
            outer, pending, prefix = [], [], None

    result: dict[str, tuple[bool | None, bool | None]] = {}
    for name, labels in seen.items():
        hookups = {h for h, _ in labels}
        walk_in = {w for _, w in labels}
        result[name] = (
            hookups.pop() if len(hookups) == 1 else None,
            walk_in.pop() if len(walk_in) == 1 else None,
        )
    return result


def wa_site_fit(
    name: str, allowed: list[dict] | None, loop_description: str | None,
) -> SiteFit:
    """Fit for one WA site: equipment plus hookups / walk-in from its loop."""
    fit = fit_from_wa_equipment(allowed)
    key = normalize_site_name(name)
    if key is None or not loop_description:
        return fit
    hookups, walk_in = parse_loop_site_types(loop_description).get(key, (None, None))
    return fit.model_copy(update={"hookups": hookups, "walk_in": walk_in})


# ---------------------------------------------------------------------------
# Recreation.gov: campsite_type only (no lengths in the availability API)
# ---------------------------------------------------------------------------

_NO_CAMPING_GEAR = ("CABIN", "YURT", "LOOKOUT", "SHELTER", "TEPEE")


def fit_from_recgov_type(campsite_type: str) -> SiteFit:
    """Conservative fit from e.g. "TENT ONLY NONELECTRIC" or "RV ELECTRIC"."""
    t = (campsite_type or "").upper()
    hookups = False if "NONELECTRIC" in t else True if "ELECTRIC" in t else None
    if any(word in t for word in _NO_CAMPING_GEAR):
        return SiteFit(fits_tent=False, fits_van=False, fits_rv=False, hookups=hookups)
    if "WALK TO" in t or "HIKE TO" in t:
        return SiteFit(fits_tent=True, fits_van=False, fits_rv=False, walk_in=True)
    if "TENT ONLY" in t:
        return SiteFit(fits_tent=True, fits_van=False, fits_rv=False, hookups=hookups)
    if re.search(r"\bRV\b", t):
        return SiteFit(fits_van=True, fits_rv=True, hookups=hookups, walk_in=False)
    if "STANDARD" in t:
        return SiteFit(hookups=hookups, walk_in=False)
    return SiteFit(hookups=hookups)


# ---------------------------------------------------------------------------
# ReserveAmerica (Oregon): per-site attributes
# ---------------------------------------------------------------------------


def fit_from_ra_attributes(
    prod_grp: str,
    categories: list[str] | None,
    max_vehicle_ft: str | None,
    electric: str | None,
) -> SiteFit:
    """Fit from RA's "Looking For Category", "Maximum Vehicle Length" and
    "Electricity Hookup" attributes. Without categories, only hookups."""
    hookups = True if electric else None
    walk_in = True if "WALK" in (prod_grp or "").upper() else None
    if categories is None:
        return SiteFit(hookups=hookups, walk_in=walk_in)
    cats = {c.lower() for c in categories}
    fits_rv = bool(cats & {"rv site", "trailer site"})
    max_rv_ft = None
    if fits_rv and max_vehicle_ft and max_vehicle_ft.strip().isdigit():
        max_rv_ft = int(max_vehicle_ft)
    return SiteFit(
        fits_tent="tent site" in cats,
        fits_van=fits_rv,
        fits_rv=fits_rv,
        max_rv_ft=max_rv_ft,
        hookups=bool(electric),
        walk_in=walk_in,
    )
