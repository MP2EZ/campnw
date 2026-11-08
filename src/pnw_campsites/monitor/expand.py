"""Template watch expansion — resolves search params to facility IDs."""

from __future__ import annotations

import json
import logging

from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import Campground

_logger = logging.getLogger(__name__)

MAX_EXPANDED = 20


def expand_template(
    search_params_json: str,
    registry: CampgroundRegistry,
) -> list[Campground]:
    """Expand template watch search params to the campgrounds it matches.

    Caps at MAX_EXPANDED, sorted by drive time (closest first).
    """
    try:
        params = json.loads(search_params_json)
    except (json.JSONDecodeError, TypeError):
        _logger.warning("Invalid search_params JSON: %s", search_params_json)
        return []

    candidates = registry.search(
        state=params.get("state"),
        tags=params.get("tags"),
        max_drive_minutes=params.get("max_drive"),
        name_like=params.get("name"),
    )

    # Sort by drive time (closest first), nulls last
    candidates.sort(
        key=lambda c: c.drive_minutes_from_base if c.drive_minutes_from_base else 9999,
    )

    return candidates[:MAX_EXPANDED]
