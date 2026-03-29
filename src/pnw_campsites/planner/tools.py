"""Tool definitions and executors for the trip planner agent."""

from __future__ import annotations

import json
import logging
from datetime import date

from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import SearchEngine, SearchQuery

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (Anthropic function-calling format)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "search_campgrounds",
        "description": (
            "Search for campgrounds with availability in the Pacific Northwest. "
            "Returns campgrounds with available dates, site counts, tags, and booking URLs. "
            "Always call this before recommending any campground."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date YYYY-MM-DD",
                },
                "state": {
                    "type": "string",
                    "enum": ["WA", "OR", "ID", "MT", "WY", "CA"],
                    "description": "State filter",
                },
                "nights": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 14,
                    "description": "Minimum consecutive nights required",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Tags to filter by. Available: lakeside, riverside, "
                        "beach, old-growth, forest, alpine, desert, backcountry, "
                        "remote, rv-friendly, tent-only, walk-in, pull-through, "
                        "group-sites, dispersed, trails, swimming, fishing, "
                        "boating, boat-launch, equestrian, climbing, "
                        "winter-camping, pet-friendly, kid-friendly, accessible, "
                        "campfire, shade, hot-springs, waterfall"
                    ),
                },
                "from_location": {
                    "type": "string",
                    "description": (
                        "Origin city for drive time. Known bases: "
                        "seattle, bellevue, portland, spokane, bellingham, moscow. "
                        "Or pass any address to geocode."
                    ),
                },
                "max_drive_minutes": {
                    "type": "integer",
                    "description": "Maximum drive time in minutes from from_location",
                },
                "name": {
                    "type": "string",
                    "description": "Search by campground name (partial match)",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "check_availability",
        "description": (
            "Check availability for a specific campground by facility ID. "
            "Use when you have a specific facility_id from a prior search result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "facility_id": {
                    "type": "string",
                    "description": "Facility ID from the registry (e.g. '232465')",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date YYYY-MM-DD",
                },
                "nights": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Minimum consecutive nights",
                },
                "source": {
                    "type": "string",
                    "enum": ["recgov", "wa_state"],
                    "description": "Booking system (default: recgov)",
                },
            },
            "required": ["facility_id", "start_date", "end_date"],
        },
    },
    {
        "name": "get_drive_time",
        "description": "Estimate drive time in minutes between two lat/lon coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_lat": {"type": "number"},
                "from_lon": {"type": "number"},
                "to_lat": {"type": "number"},
                "to_lon": {"type": "number"},
            },
            "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
        },
    },
    {
        "name": "get_campground_detail",
        "description": (
            "Get detailed info about a campground from the local registry: "
            "location, tags, vibe, notes, total sites, drive time from Seattle."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "facility_id": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["recgov", "wa_state"],
                    "description": "Booking system (default: recgov)",
                },
            },
            "required": ["facility_id"],
        },
    },
    {
        "name": "geocode_address",
        "description": "Convert an address or city name to latitude/longitude coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Address or city name to geocode",
                },
            },
            "required": ["address"],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


async def execute_tool(
    name: str,
    tool_input: dict,
    engine: SearchEngine,
    registry: CampgroundRegistry,
) -> str:
    """Execute a tool and return a compact JSON string result."""
    try:
        if name == "search_campgrounds":
            return await _search_campgrounds(tool_input, engine)
        elif name == "check_availability":
            return await _check_availability(tool_input, engine, registry)
        elif name == "get_drive_time":
            return _get_drive_time(tool_input)
        elif name == "get_campground_detail":
            return _get_campground_detail(tool_input, registry)
        elif name == "geocode_address":
            return await _geocode_address(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        logger.warning("Tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------


async def _search_campgrounds(tool_input: dict, engine: SearchEngine) -> str:
    from pnw_campsites.urls import recgov_availability_url, wa_state_availability_url

    start = date.fromisoformat(tool_input["start_date"])
    end = date.fromisoformat(tool_input["end_date"])

    booking_system = None
    source = tool_input.get("source")
    if source:
        booking_system = BookingSystem(source)

    query = SearchQuery(
        start_date=start,
        end_date=end,
        state=tool_input.get("state"),
        tags=tool_input.get("tags"),
        min_consecutive_nights=tool_input.get("nights", 1),
        from_location=tool_input.get("from_location"),
        max_drive_minutes=tool_input.get("max_drive_minutes"),
        name_like=tool_input.get("name"),
        booking_system=booking_system,
        max_campgrounds=20,
    )

    results = await engine.search(query, _skip_diagnosis=True)

    # Return top 5 — LLM context is precious
    top = results.results[:5]
    out = []
    for r in top:
        cg = r.campground
        if cg.booking_system == BookingSystem.WA_STATE:
            avail_url = wa_state_availability_url(
                cg.facility_id, start, end,
            )
        else:
            avail_url = recgov_availability_url(
                cg.facility_id, start,
            )

        # Compact window summary — just earliest window per site
        unique_sites: dict[str, dict] = {}
        for w in r.available_windows:
            if w.campsite_id not in unique_sites:
                unique_sites[w.campsite_id] = {
                    "site": w.site_name,
                    "start": w.start_date,
                    "end": w.end_date,
                    "nights": w.nights,
                }

        out.append({
            "facility_id": cg.facility_id,
            "name": cg.name,
            "state": cg.state,
            "booking_system": cg.booking_system.value,
            "tags": cg.tags,
            "vibe": cg.vibe,
            "available_sites": r.total_available_sites,
            "fcfs_sites": r.fcfs_sites,
            "drive_minutes": r.estimated_drive_minutes,
            "earliest_windows": list(unique_sites.values())[:3],
            "booking_url": avail_url,
        })

    return json.dumps({
        "found": len(out),
        "total_checked": results.campgrounds_checked,
        "campgrounds": out,
    })


async def _check_availability(
    tool_input: dict,
    engine: SearchEngine,
    registry: CampgroundRegistry,
) -> str:
    from pnw_campsites.urls import recgov_availability_url, wa_state_availability_url

    facility_id = tool_input["facility_id"]
    start = date.fromisoformat(tool_input["start_date"])
    end = date.fromisoformat(tool_input["end_date"])
    nights = tool_input.get("nights", 1)

    source = tool_input.get("source")
    booking_system = BookingSystem(source) if source else None

    result = await engine.check_specific(
        facility_id=facility_id,
        start_date=start,
        end_date=end,
        min_nights=nights,
        booking_system=booking_system,
    )

    cg = result.campground
    resolved_system = booking_system or BookingSystem.RECGOV

    if resolved_system == BookingSystem.WA_STATE:
        avail_url = wa_state_availability_url(
            facility_id, start, end,
        )
    else:
        avail_url = recgov_availability_url(facility_id, start)

    if result.error:
        return json.dumps({
            "facility_id": facility_id,
            "name": cg.name,
            "error": result.error,
        })

    # Summarise windows — group by site, show first 3 windows per site
    site_windows: dict[str, list[dict]] = {}
    for w in result.available_windows:
        site_windows.setdefault(w.campsite_id, [])
        if len(site_windows[w.campsite_id]) < 3:
            site_windows[w.campsite_id].append({
                "start": w.start_date,
                "end": w.end_date,
                "nights": w.nights,
                "type": w.campsite_type,
            })

    return json.dumps({
        "facility_id": facility_id,
        "name": cg.name,
        "state": cg.state,
        "available_sites": result.total_available_sites,
        "fcfs_sites": result.fcfs_sites,
        "site_windows": dict(list(site_windows.items())[:5]),
        "booking_url": avail_url,
    })


def _get_drive_time(tool_input: dict) -> str:
    from pnw_campsites.geo import estimated_drive_minutes

    minutes = estimated_drive_minutes(
        tool_input["from_lat"],
        tool_input["from_lon"],
        tool_input["to_lat"],
        tool_input["to_lon"],
    )
    hours, mins = divmod(minutes, 60)
    readable = f"{hours}h {mins}m" if hours else f"{mins}m"
    return json.dumps({"drive_minutes": minutes, "readable": readable})


def _get_campground_detail(tool_input: dict, registry: CampgroundRegistry) -> str:
    facility_id = tool_input["facility_id"]
    source = tool_input.get("source")
    booking_system = BookingSystem(source) if source else BookingSystem.RECGOV

    cg = registry.get_by_facility_id(facility_id, booking_system=booking_system)
    if not cg:
        return json.dumps({"error": f"Campground {facility_id} not found in registry"})

    return json.dumps({
        "facility_id": cg.facility_id,
        "name": cg.name,
        "state": cg.state,
        "region": cg.region,
        "booking_system": cg.booking_system.value,
        "latitude": cg.latitude,
        "longitude": cg.longitude,
        "tags": cg.tags,
        "vibe": cg.vibe,
        "notes": cg.notes,
        "rating": cg.rating,
        "total_sites": cg.total_sites,
        "drive_minutes_from_seattle": cg.drive_minutes_from_base,
    })


async def _geocode_address(tool_input: dict) -> str:
    from pnw_campsites.geo import geocode_address, is_known_base, resolve_base

    address = tool_input["address"]

    # Check known bases first (no network call)
    if is_known_base(address):
        lat, lon = resolve_base(address)
        return json.dumps({"lat": lat, "lon": lon, "source": "known_base"})

    lat, lon = await geocode_address(address)
    return json.dumps({"lat": lat, "lon": lon, "source": "nominatim"})
