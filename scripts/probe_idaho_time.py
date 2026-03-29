"""
Probe Idaho Time (getoutside.idaho.gov) for API endpoints.

Idaho migrated from ReserveAmerica to Brandt Information Services in Jan 2025.
This script explores the new platform for usable availability APIs.
"""

import json
from curl_cffi import requests as cffi_requests

BASE = "https://getoutside.idaho.gov"

# Chrome-like headers (same approach as GoingToCamp provider)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def probe(label: str, url: str, method: str = "GET", json_body: dict | None = None):
    """Probe a URL and report what we get back."""
    print(f"\n{'='*60}")
    print(f"[{label}] {method} {url}")
    print(f"{'='*60}")
    try:
        if method == "GET":
            resp = cffi_requests.get(url, headers=HEADERS, impersonate="chrome131", timeout=15)
        else:
            resp = cffi_requests.post(
                url, headers={**HEADERS, "Content-Type": "application/json"},
                json=json_body, impersonate="chrome131", timeout=15
            )
        print(f"Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
        print(f"Content-Length: {len(resp.content)} bytes")

        # Check for redirects
        if resp.url != url:
            print(f"Redirected to: {resp.url}")

        # Check for common API indicators
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try:
                data = resp.json()
                print(f"JSON response (truncated):")
                print(json.dumps(data, indent=2)[:2000])
            except Exception:
                print(f"Body (first 1000 chars): {resp.text[:1000]}")
        elif "html" in ct:
            # Look for SPA indicators, API base URLs, etc.
            text = resp.text
            print(f"HTML response — scanning for API clues...")

            # Look for common SPA patterns
            for pattern in ["api/", "apiUrl", "baseUrl", "API_BASE", "apiBase",
                            "graphql", "/v1/", "/v2/", "swagger", "openapi",
                            "brandt", "reservation", "availability", "campground",
                            "facility", "booking", "__NEXT_DATA__", "window.__"]:
                idx = text.lower().find(pattern.lower())
                if idx >= 0:
                    start = max(0, idx - 80)
                    end = min(len(text), idx + 120)
                    snippet = text[start:end].replace("\n", " ").strip()
                    print(f"  Found '{pattern}': ...{snippet}...")

            # Look for script tags with src (API config often in JS bundles)
            import re
            scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text)
            if scripts:
                print(f"\n  Script sources ({len(scripts)}):")
                for s in scripts[:15]:
                    print(f"    {s}")

            # Look for meta tags
            metas = re.findall(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*name=["\']([^"\']*)["\']', text)
            metas += re.findall(r'<meta[^>]+name=["\']([^"\']*)["\'][^>]*content=["\']([^"\']*)["\']', text)
            if metas:
                print(f"\n  Meta tags:")
                for m in metas[:10]:
                    print(f"    {m}")
        else:
            print(f"Body (first 500 chars): {resp.text[:500]}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")


def main():
    print("=" * 60)
    print("IDAHO TIME (getoutside.idaho.gov) API PROBE")
    print("=" * 60)

    # 1. Homepage — look for SPA framework, API base URLs
    probe("Homepage", BASE)

    # 2. Common API path patterns
    for path in [
        "/api",
        "/api/v1",
        "/api/facilities",
        "/api/campgrounds",
        "/api/availability",
        "/api/parks",
        "/api/reservations",
        "/api/search",
        "/api/maps",
        "/api/locations",
    ]:
        probe(f"API path", f"{BASE}{path}")

    # 3. Brandt-specific patterns (their other products use these)
    for path in [
        "/rdr/fd/places",           # UseDirect pattern (just in case)
        "/rdr/search/grid",         # UseDirect availability
        "/camping",
        "/camping/search",
        "/parks",
        "/reservations",
        "/search",
    ]:
        probe(f"Alt path", f"{BASE}{path}")

    # 4. Check for a separate API subdomain
    for subdomain in [
        "https://api.getoutside.idaho.gov",
        "https://reservations.getoutside.idaho.gov",
        "https://booking.getoutside.idaho.gov",
    ]:
        probe(f"Subdomain", subdomain)


if __name__ == "__main__":
    main()
