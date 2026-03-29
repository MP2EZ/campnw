"""
Probe ReserveAmerica for Oregon State Parks API endpoints.

Tests:
1. Mobile API (api.reserveamerica.com) — JSON endpoint, may bypass WAF
2. Main site with curl_cffi — test if TLS fingerprinting bypasses bot protection
3. ACTIVE Network official API — metadata only (no availability) but useful for park IDs
"""

import json
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Known Oregon park IDs from research
FORT_STEVENS_ID = "402178"
SILVER_FALLS_ID = "402235"


def probe(label: str, url: str, method: str = "GET", json_body: dict | None = None,
          extra_headers: dict | None = None, impersonate: str = "chrome131"):
    """Probe a URL and report what we get back."""
    print(f"\n{'='*60}")
    print(f"[{label}] {method} {url}")
    print(f"{'='*60}")
    hdrs = {**HEADERS, **(extra_headers or {})}
    try:
        if method == "GET":
            resp = cffi_requests.get(url, headers=hdrs, impersonate=impersonate, timeout=15, allow_redirects=True)
        else:
            resp = cffi_requests.post(
                url, headers={**hdrs, "Content-Type": "application/json"},
                json=json_body, impersonate=impersonate, timeout=15, allow_redirects=True
            )
        print(f"Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
        print(f"Content-Length: {len(resp.content)} bytes")

        if resp.url != url:
            print(f"Redirected to: {resp.url}")

        # Show interesting response headers
        for h in ["server", "x-powered-by", "x-frame-options", "set-cookie",
                   "cf-ray", "x-cache", "via", "x-amz-cf-id"]:
            val = resp.headers.get(h)
            if val:
                print(f"  {h}: {val[:200]}")

        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try:
                data = resp.json()
                print(f"JSON response:")
                print(json.dumps(data, indent=2)[:3000])
            except Exception:
                print(f"Body (first 1000): {resp.text[:1000]}")
        elif "xml" in ct:
            print(f"XML response (first 2000):")
            print(resp.text[:2000])
        elif "html" in ct:
            text = resp.text
            # Check if it's a bot challenge page
            for indicator in ["captcha", "challenge", "cf-browser-verification",
                              "just a moment", "checking your browser", "access denied",
                              "blocked", "robot", "bot"]:
                if indicator.lower() in text.lower():
                    idx = text.lower().find(indicator.lower())
                    start = max(0, idx - 50)
                    end = min(len(text), idx + 100)
                    print(f"  ⚠ Bot protection indicator '{indicator}': ...{text[start:end].strip()}...")

            # Look for API clues in HTML
            import re
            for pattern in ["api/", "apiUrl", "baseUrl", "/jaxrs", "/products/",
                            "availability", "campground", "facility", "parkId"]:
                idx = text.lower().find(pattern.lower())
                if idx >= 0:
                    start = max(0, idx - 60)
                    end = min(len(text), idx + 100)
                    print(f"  API clue '{pattern}': ...{text[start:end].replace(chr(10), ' ').strip()}...")

            # Title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
            if title_match:
                print(f"  Page title: {title_match.group(1).strip()}")

            print(f"  HTML length: {len(text)} chars")
        else:
            print(f"Body (first 500): {resp.text[:500]}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")


def main():
    print("=" * 60)
    print("RESERVE AMERICA / OREGON STATE PARKS API PROBE")
    print("=" * 60)

    # ---- SECTION 1: Mobile API (most promising) ----
    print("\n\n>>> SECTION 1: ReserveAmerica Mobile API <<<\n")

    # The undocumented mobile JSON API
    probe("Mobile API root", "https://api.reserveamerica.com")

    # Campsite products endpoint (discovered by camply community)
    probe(
        "Mobile: Fort Stevens campsites",
        f"https://api.reserveamerica.com/jaxrs-json/products/OR/{FORT_STEVENS_ID}/campsites"
    )

    probe(
        "Mobile: Silver Falls campsites",
        f"https://api.reserveamerica.com/jaxrs-json/products/OR/{SILVER_FALLS_ID}/campsites"
    )

    # Try other mobile API patterns
    probe(
        "Mobile: facility details",
        f"https://api.reserveamerica.com/jaxrs-json/products/OR/{FORT_STEVENS_ID}"
    )

    probe(
        "Mobile: OR parks list",
        "https://api.reserveamerica.com/jaxrs-json/products/OR"
    )

    # ---- SECTION 2: Main site with curl_cffi bypass ----
    print("\n\n>>> SECTION 2: Main Site (curl_cffi TLS bypass) <<<\n")

    # Can curl_cffi's Chrome impersonation bypass the WAF?
    probe(
        "Main site homepage",
        "https://oregonstateparks.reserveamerica.com"
    )

    # Campground directory (lists all parks)
    probe(
        "Campground directory",
        "https://oregonstateparks.reserveamerica.com/camping/oregon-state-parks/r/campgroundDirectoryList.do?contractCode=OR"
    )

    # Specific campground availability search (HTML form endpoint)
    probe(
        "Fort Stevens search",
        f"https://oregonstateparks.reserveamerica.com/campsiteSearch.do?contractCode=OR&parkId={FORT_STEVENS_ID}"
    )

    # ---- SECTION 3: Check if OR has any UseDirect footprint ----
    print("\n\n>>> SECTION 3: UseDirect / Tyler check <<<\n")

    # Some states have migrated — check common UseDirect patterns
    for domain in [
        "https://oregon.reserveamerica.com",
        "https://reservations.oregonstateparks.org",
        "https://camping.oregonstateparks.org",
    ]:
        probe(f"UseDirect check", domain)

    # ---- SECTION 4: ACTIVE Network official API (metadata) ----
    print("\n\n>>> SECTION 4: ACTIVE Network API (metadata only) <<<\n")

    # This is documented and works — but only returns metadata, no availability
    # Still useful for getting park IDs and details
    probe(
        "ACTIVE: OR campgrounds",
        "http://api.amp.active.com/camping/campgrounds?pstate=OR&api_key=demo"
    )

    # Check for Oregon parks on the main reserveamerica.com search
    probe(
        "RA unified search",
        "https://www.reserveamerica.com/unifSearch.do?contractCode=OR"
    )


if __name__ == "__main__":
    main()
