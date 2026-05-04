#!/usr/bin/env python3
"""
PNW Campsite Tool — API Validation Script
==========================================
Tests the key API surfaces we'd build on:

1. Recreation.gov RIDB (official, documented) — campground metadata
2. Recreation.gov Availability (undocumented) — real-time site availability
3. WA State Parks / GoingToCamp — state park availability
4. Oregon State Parks / ReserveAmerica — state park availability (stretch)

Run: python validate_camping_apis.py
No API key needed for initial validation (RIDB key needed for production use).
"""

import time
from datetime import datetime
from typing import Any

import requests

# ============================================================================
# Configuration — known PNW campground IDs for testing
# ============================================================================

TEST_CAMPGROUNDS = {
    "ohanapecosh": {
        "facility_id": "232464",
        "name": "Ohanapecosh Campground",
        "location": "Mt. Rainier NP",
    },
    "cougar_rock": {
        "facility_id": "232463",
        "name": "Cougar Rock Campground",
        "location": "Mt. Rainier NP",
    },
}

WA_GOINGTOCAMP_BASE = "https://washington.goingtocamp.com"

# ============================================================================
# Test 1: Recreation.gov RIDB API (Official/Documented)
# ============================================================================

def test_ridb_api():
    """
    Tests the official RIDB API for campground metadata.
    Full usage requires a free API key from ridb.recreation.gov.
    """
    print("\n" + "=" * 70)
    print("TEST 1: Recreation.gov RIDB API (Campground Metadata)")
    print("=" * 70)

    url = "https://ridb.recreation.gov/api/v1/facilities"
    params = {
        "state": "WA",
        "activity": "CAMPING",
        "limit": 5,
        "offset": 0,
    }
    headers = {
        "accept": "application/json",
        # "apikey": "YOUR_API_KEY"  # Uncomment and add key for production
    }

    print("\n[1a] Searching for WA campgrounds via RIDB...")
    print(f"     URL: {url}")
    print(f"     Params: {params}")

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"     Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            facilities = data.get("RECDATA", [])
            total = data.get("METADATA", {}).get("RESULTS", {}).get("TOTAL_COUNT", "?")
            print(f"     OK Success! Found {total} total facilities, showing first {len(facilities)}")
            for f in facilities[:3]:
                print(f"        - {f.get('FacilityName', '?')} (ID: {f.get('FacilityID', '?')})")
            return True
        elif resp.status_code == 401:
            print("     !!  401 Unauthorized — API key required")
            print("        Sign up at: https://ridb.recreation.gov (free)")
            return "needs_key"
        else:
            print(f"     XX Unexpected status: {resp.status_code}")
            print(f"     Response: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"     XX Error: {e}")
        return False


# ============================================================================
# Test 2: Recreation.gov Availability API (Undocumented)
# ============================================================================

def test_recgov_availability():
    """
    Tests the undocumented but widely-used availability endpoint.
    This is the critical one — every campsite checker tool uses it.
    """
    print("\n" + "=" * 70)
    print("TEST 2: Recreation.gov Availability API (Undocumented)")
    print("=" * 70)

    facility_id = "232464"  # Ohanapecosh
    target_date = datetime(2026, 7, 1)
    start_date = target_date.strftime("%Y-%m-01T00:00:00.000Z")

    url = f"https://www.recreation.gov/api/camps/availability/campground/{facility_id}/month"
    params = {"start_date": start_date}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    print(f"\n[2a] Checking availability at Ohanapecosh for {target_date.strftime('%B %Y')}...")
    print(f"     URL: {url}")
    print(f"     Params: {params}")

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"     Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            campsites = data.get("campsites", {})
            print(f"     OK Success! Got availability for {len(campsites)} campsites")

            available_count = 0
            reserved_count = 0
            sample_site = None

            for _site_id, site_data in list(campsites.items())[:50]:
                availabilities = site_data.get("availabilities", {})
                for _date_str, status in availabilities.items():
                    if status == "Available":
                        available_count += 1
                    elif status == "Reserved":
                        reserved_count += 1
                if sample_site is None:
                    sample_site = site_data

            print(f"     Available slots (first 50 sites): {available_count}")
            print(f"     Reserved slots (first 50 sites): {reserved_count}")

            if sample_site:
                print("\n     Sample campsite data structure:")
                print(f"       campsite_id: {sample_site.get('campsite_id')}")
                print(f"       site: {sample_site.get('site')}")
                print(f"       loop: {sample_site.get('loop')}")
                print(f"       campsite_type: {sample_site.get('campsite_type')}")
                print(f"       type_of_use: {sample_site.get('type_of_use')}")
                print(f"       min/max_people: {sample_site.get('min_num_people')}/{sample_site.get('max_num_people')}")

                avail = sample_site.get("availabilities", {})
                sorted_dates = sorted(avail.keys())[:7]
                print("       First week availability:")
                for d in sorted_dates:
                    status = avail[d]
                    indicator = "[OPEN]" if status == "Available" else "[TAKEN]" if status == "Reserved" else "[--]"
                    print(f"         {indicator} {d[:10]}: {status}")
            return True
        else:
            print(f"     XX Status: {resp.status_code}")
            print(f"     Response: {resp.text[:500]}")
            return False
    except Exception as e:
        print(f"     XX Error: {e}")
        return False


# ============================================================================
# Test 2b: Recreation.gov Search API
# ============================================================================

def test_recgov_search():
    """Tests the recreation.gov search/suggest API for campground discovery."""
    print("\n" + "=" * 70)
    print("TEST 2b: Recreation.gov Search API")
    print("=" * 70)

    url = "https://www.recreation.gov/api/search"
    params = {"q": "camping", "fq": "state:WA", "size": 5, "start": 0}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    print("\n[2b] Searching recreation.gov for campgrounds in WA...")

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"     Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            total = data.get("total", "?")
            print(f"     OK Success! {total} total results, showing first {len(results)}")
            for r in results[:5]:
                print(f"        - [{r.get('entity_type', '?')}] {r.get('name', '?')} (ID: {r.get('entity_id', '?')})")
            return True
        else:
            print(f"     XX Status: {resp.status_code}")
            print(f"     Response: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"     XX Error: {e}")
        return False


# ============================================================================
# Test 3: WA State Parks / GoingToCamp API
# ============================================================================

def test_wa_goingtocamp():
    """Tests the GoingToCamp API used by Washington State Parks."""
    print("\n" + "=" * 70)
    print("TEST 3: WA State Parks / GoingToCamp API")
    print("=" * 70)

    base = WA_GOINGTOCAMP_BASE
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    success = True

    # Step 1: Maps
    print("\n[3a] Fetching WA State Parks map data...")
    try:
        resp = requests.get(f"{base}/api/maps", headers=headers, timeout=15)
        print(f"     Status: {resp.status_code}")
        if resp.status_code == 200:
            maps = resp.json()
            print(f"     OK Got {len(maps)} map entries")
            for m in maps[:3]:
                print(f"        - Map ID: {m.get('mapId')}, Name: {m.get('name', '?')}")
        else:
            print(f"     !!  Status: {resp.status_code}")
            success = False
    except Exception as e:
        print(f"     XX Error: {e}")
        success = False

    # Step 2: Resource categories
    print("\n[3b] Fetching resource categories...")
    try:
        resp = requests.get(f"{base}/api/resourcecategory", headers=headers, timeout=15)
        print(f"     Status: {resp.status_code}")
        if resp.status_code == 200:
            categories = resp.json()
            print(f"     OK Got {len(categories)} resource categories")
            for c in categories[:5]:
                print(f"        - ID: {c.get('resourceCategoryId')}, Name: {c.get('name', '?')}")
        else:
            print(f"     !!  Status: {resp.status_code}")
    except Exception as e:
        print(f"     XX Error: {e}")

    # Step 3: Availability
    print("\n[3c] Testing availability search...")
    payload = {
        "mapId": -2147483648,
        "bookingCategoryId": 0,
        "startDate": "2026-07-10",
        "endDate": "2026-07-12",
        "isReserving": True,
        "getDailyAvailability": False,
        "partySize": 2,
        "equipmentCategoryId": -32768,
        "subEquipmentCategoryId": -32768,
        "generateBreadcrumbs": False,
    }

    try:
        resp = requests.post(f"{base}/api/availability/map", json=payload, headers=headers, timeout=15)
        print(f"     Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                map_items = data.get("mapLinkAvailabilities", [])
                resource_avail = data.get("resourceAvailabilities", [])
                print("     OK Got response!")
                print(f"        mapLinkAvailabilities: {len(map_items)} entries")
                print(f"        resourceAvailabilities: {len(resource_avail)} entries")
                for item in map_items[:5]:
                    print(f"        - Link {item.get('mapLinkId')}: availability={item.get('availability')}")
            return success
        else:
            print(f"     !!  Status: {resp.status_code}")
            print(f"     Response: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"     XX Error: {e}")
        return False


# ============================================================================
# Test 4: Oregon State Parks / ReserveAmerica (stretch)
# ============================================================================

def test_or_reserveamerica():
    """Tests Oregon State Parks via ReserveAmerica/Aspira — most fragile integration."""
    print("\n" + "=" * 70)
    print("TEST 4: Oregon State Parks / ReserveAmerica (Stretch)")
    print("=" * 70)

    url = "https://oregonstateparks.reserveamerica.com/campsiteCalendar.do"
    params = {
        "page": "calendar",
        "contractCode": "OR",
        "parkId": "402169",  # Fort Stevens
        "calarvdt": "2026-07-10",
        "sitepage": "true",
        "startIdx": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print("\n[4a] Testing ReserveAmerica availability endpoint...")
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15, allow_redirects=True)
        print(f"     Status: {resp.status_code}")
        print(f"     Content-Type: {resp.headers.get('content-type', '?')}")
        print(f"     Response size: {len(resp.text)} bytes")

        if resp.status_code == 200:
            if "availability" in resp.text.lower() or "campsite" in resp.text.lower():
                print("     OK Got page with camping content (HTML scraping needed)")
            elif "javascript" in resp.text.lower() and len(resp.text) < 1000:
                print("     !!  Got JS redirect — needs headless browser (Playwright)")
            else:
                print("     !!  Got response but unclear content")
                print(f"        First 200 chars: {resp.text[:200]}")
            return "partial"
        else:
            print(f"     XX Status: {resp.status_code}")
            return False
    except Exception as e:
        print(f"     XX Error: {e}")
        return False


# ============================================================================
# Summary
# ============================================================================

def print_summary(results: dict[str, Any]):
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    status_map = {
        True: "OK WORKING",
        False: "XX FAILED",
        "partial": "!!  PARTIAL (needs scraping/headless)",
        "needs_key": "KEY NEEDS API KEY (free signup)",
    }

    for name, result in results.items():
        status = status_map.get(result, f"?? {result}")
        print(f"  {status:45s} {name}")

    print("\n" + "-" * 70)
    print("RECOMMENDATION:")
    print("-" * 70)

    rec_avail = results.get("Recreation.gov Availability")
    wa_parks = results.get("WA State Parks (GoingToCamp)")

    if rec_avail and wa_parks:
        print("  Both primary data sources working — ready for Phase 1")
    elif rec_avail:
        print("  Recreation.gov working — start there, add WA State Parks later")
    else:
        print("  Review individual test results above")
    print()


def main():
    print("=" * 70)
    print("PNW CAMPSITE TOOL — API VALIDATION")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    results = {}

    results["Recreation.gov RIDB (metadata)"] = test_ridb_api()
    time.sleep(1)
    results["Recreation.gov Availability"] = test_recgov_availability()
    time.sleep(1)
    results["Recreation.gov Search"] = test_recgov_search()
    time.sleep(1)
    results["WA State Parks (GoingToCamp)"] = test_wa_goingtocamp()
    time.sleep(1)
    results["OR State Parks (ReserveAmerica)"] = test_or_reserveamerica()

    print_summary(results)


if __name__ == "__main__":
    main()
