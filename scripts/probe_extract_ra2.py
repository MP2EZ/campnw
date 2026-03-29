"""Extract the full data structure from RA availability page using proper JSON parsing."""

import json
import re
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

url = "https://www.reserveamerica.com/explore/fort-stevens-state-park/OR/402178/campsite-availability"
print(f"Fetching {url}...")
resp = cffi_requests.get(url, headers=HEADERS, impersonate="chrome131", timeout=30)
html = resp.text
print(f"Got {len(html)} chars")

# The page is an SSR React app. The data is in script tags.
# Find all <script> tags with inline content (not src)
scripts = re.findall(r'<script(?:\s+[^>]*)?>([^<]{500,})</script>', html)
print(f"\nFound {len(scripts)} large inline scripts")

for i, script in enumerate(scripts):
    print(f"\n--- Script {i}: {len(script)} chars ---")
    # Look for JSON data assignments
    if "resultsMap" in script or "siteAvail" in script or "campsite" in script.lower():
        print("  Contains availability data!")
        # Try to find the data object — often it's window.__PRELOADED_STATE__ or similar
        # Or it might be in a React hydration call

        # Find key data snippets
        for pat in ["sitesAvailability", "campsiteList", "siteAvail", "availabilityMap",
                     "resultsMap", "inventoryMap", "bookingSite"]:
            idx = script.find(pat)
            if idx >= 0:
                print(f"  '{pat}' at offset {idx}: ...{script[idx:idx+300]}...")

    elif "self.__next" in script or "__NEXT" in script:
        print("  Next.js chunk")
        # These are the RSC/SSR chunks
        if "availability" in script.lower() or "campsite" in script.lower():
            # Find relevant data in this chunk
            for pat in ["siteAvail", "campsite", "availability", "Available", "Reserved"]:
                idx = script.lower().find(pat.lower())
                if idx >= 0:
                    print(f"  '{pat}' at {idx}: ...{script[idx:idx+200]}...")
                    break
    else:
        # Show first 200 chars for context
        print(f"  Preview: {script[:200]}")

# Alternative: search for JSON data between specific markers
print("\n\n=== Searching for campsite data objects ===")

# Look for siteName patterns (campsite objects)
site_names = re.findall(r'"siteName"\s*:\s*"([^"]+)"', html)
if site_names:
    print(f"\nFound {len(site_names)} siteNames: {site_names[:10]}...")

# Look for availability status values
statuses = re.findall(r'"(?:status|availabilityStatus)"\s*:\s*"([^"]+)"', html)
if statuses:
    from collections import Counter
    counts = Counter(statuses)
    print(f"\nAvailability statuses: {dict(counts)}")

# Find a single campsite object to understand the schema
site_obj = re.search(r'\{"siteId"\s*:\s*\d+[^}]{50,500}\}', html)
if site_obj:
    print(f"\nSample site object:\n{site_obj.group()[:500]}")

# Try to find the data in "self.__next_f.push" calls (React Server Components)
rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"([^"]{100,}?)"\]\)', html)
print(f"\nFound {len(rsc_chunks)} RSC chunks")
for i, chunk in enumerate(rsc_chunks[:5]):
    # Unescape the string
    unescaped = chunk.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
    if "siteAvail" in unescaped or "campsite" in unescaped.lower() or "Available" in unescaped:
        print(f"\n  RSC chunk {i} ({len(chunk)} chars) — contains availability data!")
        # Try to find JSON within
        json_match = re.search(r'\{[^{}]*"siteId"[^{}]*\}', unescaped)
        if json_match:
            print(f"  Sample: {json_match.group()[:300]}")
        # Show a relevant snippet
        for pat in ["siteAvail", "resultsMap", "campsite"]:
            idx = unescaped.find(pat)
            if idx >= 0:
                print(f"  '{pat}': {unescaped[idx:idx+400]}")
                break

# Try a broader search for the main data blob
# Often the availability grid data is in a single large JSON
print("\n\n=== Looking for large JSON blobs ===")
# Find the position of resultsMap in the raw HTML
rm_idx = html.find('"resultsMap"')
if rm_idx >= 0:
    # Walk backwards to find the start of the enclosing object
    # Then try to extract a reasonable chunk
    chunk_start = max(0, rm_idx - 100)
    chunk = html[chunk_start:chunk_start + 5000]
    # Find the key data fields
    for field in ["contractCode", "locationID", "campgroundName", "campsiteList",
                  "siteAvail", "availStatus", "maxDate", "minDate"]:
        fidx = chunk.find(field)
        if fidx >= 0:
            print(f"  '{field}' near resultsMap: ...{chunk[fidx:fidx+150]}...")
