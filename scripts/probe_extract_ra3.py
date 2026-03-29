"""Final extraction: find the campsite data and any XHR API endpoints in the RA page."""

import json
import re
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

url = "https://www.reserveamerica.com/explore/fort-stevens-state-park/OR/402178/campsite-availability"
print(f"Fetching...")
resp = cffi_requests.get(url, headers=HEADERS, impersonate="chrome131", timeout=30)
html = resp.text
print(f"Got {len(html)} chars\n")

# 1. Find all siteId values and their context
print("=== Site data sampling ===")
# Get a few site objects with surrounding context
site_ids = list(re.finditer(r'"siteId"\s*:\s*(\d+)', html))
print(f"Found {len(site_ids)} siteId references")

if site_ids:
    # Show context around first few sites
    for si in site_ids[:3]:
        pos = si.start()
        # Find the start of the enclosing object (look back for {)
        obj_start = html.rfind('{', max(0, pos - 500), pos)
        if obj_start >= 0:
            chunk = html[obj_start:obj_start + 600]
            # Try to parse as JSON fragment
            print(f"\n  Site {si.group(1)} context ({obj_start}):")
            print(f"  {chunk[:600]}")

# 2. Find fetch/API endpoint URLs in the JS bundles
print("\n\n=== JS Bundle API endpoint scan ===")
# The page loads JS bundles - find them
bundle_urls = re.findall(r'"(newra/js/[^"]+\.js)"', html)
print(f"Found {len(bundle_urls)} JS bundles")

# Check for inline fetch/XHR patterns
fetch_patterns = re.findall(r'fetch\s*\(\s*["`\']([^"`\']+)["`\']', html)
xhr_patterns = re.findall(r'\.open\s*\(\s*["\'](?:GET|POST)["\']\s*,\s*["\']([^"\']+)["\']', html)
url_patterns = re.findall(r'(?:apiUrl|apiBase|baseUrl|API_URL|AVAILABILITY_URL)\s*[=:]\s*["\']([^"\']+)["\']', html)

for label, pats in [("fetch()", fetch_patterns), ("XHR open()", xhr_patterns), ("API URLs", url_patterns)]:
    if pats:
        print(f"\n{label}:")
        for p in sorted(set(pats)):
            print(f"  {p}")

# 3. Find the availability grid API if it exists
# React apps often use getInitialProps or getServerSideProps that call internal APIs
# Look for internal API routes
internal_apis = re.findall(r'["\']/(api|_next/data)/[^"\']+["\']', html)
if internal_apis:
    print(f"\nInternal API routes: {sorted(set(internal_apis))[:20]}")

# 4. Extract availability status data
print("\n\n=== Availability data extraction ===")
# Find availability entries
avail_entries = re.findall(r'"availabilityStatus"\s*:\s*"([^"]+)"', html)
if avail_entries:
    from collections import Counter
    print(f"Availability statuses: {dict(Counter(avail_entries))}")

# Find site availability map entries
avail_map = re.findall(r'"(\d{4}-\d{2}-\d{2})"\s*:\s*\{[^}]*"(?:status|availabilityStatus)"\s*:\s*"([^"]+)"', html)
if avail_map:
    print(f"\nDate-based availability entries ({len(avail_map)} total):")
    dates = {}
    for date, status in avail_map:
        dates.setdefault(date, []).append(status)
    for d in sorted(dates.keys())[:10]:
        from collections import Counter
        print(f"  {d}: {dict(Counter(dates[d]))}")

# 5. Look for the key: campsite list with names/types
print("\n\n=== Campsite metadata ===")
site_names = re.findall(r'"siteName"\s*:\s*"([^"]*)"', html)
if site_names:
    print(f"Site names ({len(site_names)}): {site_names[:15]}...")

site_types = re.findall(r'"siteType"\s*:\s*"([^"]*)"', html)
if site_types:
    from collections import Counter
    print(f"Site types: {dict(Counter(site_types))}")

# 6. Now probe the key question: does RA have a JSON API behind the page?
print("\n\n=== JSON API probe (Accept: application/json) ===")
# Try the same URL but requesting JSON
for accept in ["application/json", "application/json, text/plain, */*"]:
    r = cffi_requests.get(url, headers={**HEADERS, "Accept": accept, "X-Requested-With": "XMLHttpRequest"},
                          impersonate="chrome131", timeout=15)
    ct = r.headers.get("content-type", "")
    print(f"Accept={accept[:30]}: status={r.status_code}, ct={ct[:50]}, size={len(r.content)}")
    if "json" in ct:
        try:
            data = r.json()
            print(f"  JSON keys: {list(data.keys())[:20]}")
            with open("data/ra_api_response.json", "w") as f:
                json.dump(data, f, indent=2)
            print("  Saved to data/ra_api_response.json")
        except Exception:
            print(f"  Body: {r.text[:500]}")

# 7. Try _next/data endpoint (Next.js data route)
print("\n\n=== Next.js _next/data probe ===")
# Find buildId from the page
build_id = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
if build_id:
    bid = build_id.group(1)
    print(f"Build ID: {bid}")
    # Try the data route
    data_url = f"https://www.reserveamerica.com/_next/data/{bid}/explore/fort-stevens-state-park/OR/402178/campsite-availability.json"
    r = cffi_requests.get(data_url, headers={**HEADERS, "Accept": "application/json"},
                          impersonate="chrome131", timeout=15)
    print(f"Status: {r.status_code}, CT: {r.headers.get('content-type','')[:50]}, Size: {len(r.content)}")
    if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
        try:
            data = r.json()
            print(f"Keys: {list(data.keys())}")
            with open("data/ra_nextdata_response.json", "w") as f:
                json.dump(data, f, indent=2)
            print("Saved to data/ra_nextdata_response.json")
        except Exception:
            print(f"Body: {r.text[:500]}")
    elif r.status_code == 200:
        print(f"Body preview: {r.text[:300]}")
else:
    print("No buildId found in page")
