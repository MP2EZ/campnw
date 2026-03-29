"""
Deeper probe based on initial findings:
1. Idaho: homepage has inline park data, /camping is behind AWS WAF — find the AJAX endpoints
2. ReserveAmerica: www.reserveamerica.com is a React SPA — find the API it calls
"""

import json
import re
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def probe(label, url, method="GET", json_body=None, extra_headers=None):
    hdrs = {**HEADERS, **(extra_headers or {})}
    print(f"\n{'='*60}")
    print(f"[{label}] {method} {url}")
    try:
        if method == "GET":
            resp = cffi_requests.get(url, headers=hdrs, impersonate="chrome131", timeout=15, allow_redirects=True)
        else:
            resp = cffi_requests.post(url, headers={**hdrs, "Content-Type": "application/json"},
                                      json=json_body, impersonate="chrome131", timeout=15, allow_redirects=True)
        print(f"Status: {resp.status_code} | Content-Type: {resp.headers.get('content-type', 'N/A')[:60]} | Size: {len(resp.content)}")
        if resp.url != url:
            print(f"→ Redirected to: {resp.url}")
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try:
                data = resp.json()
                print(json.dumps(data, indent=2)[:3000])
            except Exception:
                print(resp.text[:2000])
        return resp
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return None


def idaho_deep_probe():
    """Idaho Time homepage is server-rendered with jQuery.
    The booking system is at /camping behind AWS WAF.
    Strategy: extract park data from homepage, find AJAX endpoints."""

    print("\n" + "="*60)
    print("IDAHO DEEP PROBE — Extract park data & find AJAX endpoints")
    print("="*60)

    # 1. Get the homepage and extract park data
    resp = cffi_requests.get("https://getoutside.idaho.gov/", headers=HEADERS,
                             impersonate="chrome131", timeout=15)
    html = resp.text

    # Look for park data in the page (dropdown, data attributes, inline JSON)
    print("\n--- Park data extraction ---")

    # Find dropdown options (park selector)
    options = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>([^<]+)</option>', html)
    if options:
        print(f"\nDropdown options ({len(options)} total):")
        for val, name in options[:30]:
            if val and name.strip() != "Select a Park":
                print(f"  {val}: {name.strip()}")

    # Find data attributes on park elements
    data_attrs = re.findall(r'data-(?:park|facility|id|location|lat|lng|campground)[^=]*=["\']([^"\']*)["\']', html, re.IGNORECASE)
    if data_attrs:
        print(f"\nData attributes found: {data_attrs[:20]}")

    # Find inline JavaScript with park data (JSON objects, arrays)
    js_data = re.findall(r'(?:var|let|const)\s+(\w+)\s*=\s*(\[[\s\S]{20,2000}?\]);', html)
    for var_name, var_data in js_data:
        print(f"\nJS variable '{var_name}': {var_data[:500]}")

    # Find AJAX/fetch calls
    ajax_urls = re.findall(r'(?:url|fetch|ajax|get|post)\s*[\(:]?\s*["\']([^"\']+?)["\']', html, re.IGNORECASE)
    if ajax_urls:
        print(f"\nAJAX/fetch URLs found:")
        for u in set(ajax_urls):
            if '/' in u and not u.startswith('//') and 'cdn' not in u:
                print(f"  {u}")

    # Look for form actions
    forms = re.findall(r'<form[^>]*action=["\']([^"\']*)["\'][^>]*method=["\']([^"\']*)["\']', html, re.IGNORECASE)
    forms += re.findall(r'<form[^>]*method=["\']([^"\']*)["\'][^>]*action=["\']([^"\']*)["\']', html, re.IGNORECASE)
    if forms:
        print(f"\nForm actions:")
        for f in forms:
            print(f"  {f}")

    # Look for the park card data — these might have IDs/URLs
    park_cards = re.findall(r'href=["\']([^"\']*(?:park|camping|reservation|book)[^"\']*)["\']', html, re.IGNORECASE)
    if park_cards:
        print(f"\nPark/camping links ({len(park_cards)}):")
        for link in sorted(set(park_cards))[:30]:
            print(f"  {link}")

    # 2. Try /camping with a full browser session (cookies from homepage)
    print("\n--- Trying /camping with session cookies ---")
    session = cffi_requests.Session()
    # First hit homepage to get cookies
    r1 = session.get("https://getoutside.idaho.gov/", headers=HEADERS, impersonate="chrome131", timeout=15)
    print(f"Homepage cookies: {dict(session.cookies)}")

    # Now try /camping with those cookies
    r2 = session.get("https://getoutside.idaho.gov/camping/heyburn-state-park",
                      headers=HEADERS, impersonate="chrome131", timeout=15)
    print(f"/camping/heyburn-state-park: {r2.status_code}")
    if r2.status_code == 200:
        # Look for availability data
        for pat in ["availability", "calendar", "campsite", "unit", "facility", "rate"]:
            if pat in r2.text.lower():
                idx = r2.text.lower().find(pat)
                print(f"  Found '{pat}': ...{r2.text[max(0,idx-40):idx+80]}...")
    else:
        print(f"  Response: {r2.text[:500]}")

    # 3. Check if there's an API path through the Brandt system
    # Brandt often uses /ws/ or /services/ patterns
    for path in ["/ws/parks", "/services/availability", "/booking/api",
                 "/camping/api/parks", "/camping/api/availability",
                 "/camping/search", "/camping/availability"]:
        r = session.get(f"https://getoutside.idaho.gov{path}",
                       headers={**HEADERS, "Accept": "application/json"},
                       impersonate="chrome131", timeout=10)
        ct = r.headers.get("content-type", "")
        if r.status_code != 200 or "json" in ct or len(r.content) != 85822:
            print(f"  {path}: {r.status_code} ({ct[:40]}) {len(r.content)}b")
            if "json" in ct:
                print(f"    {r.text[:500]}")


def reserveamerica_spa_probe():
    """The www.reserveamerica.com unified site is a React SPA.
    It loaded a 402KB page. Find the API backend it calls."""

    print("\n" + "="*60)
    print("RESERVEAMERICA SPA PROBE — Find React app's API backend")
    print("="*60)

    # 1. Get the SPA and extract API configuration
    resp = cffi_requests.get("https://www.reserveamerica.com/explore/search-results",
                             headers=HEADERS, impersonate="chrome131", timeout=15)
    html = resp.text

    # Extract __NEXT_DATA__ or similar SSR data
    next_data = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html)
    if next_data:
        print("\n__NEXT_DATA__ found!")
        try:
            data = json.loads(next_data.group(1))
            print(json.dumps(data, indent=2)[:3000])
        except Exception:
            print(next_data.group(1)[:2000])

    # Look for API base URL, env config, etc.
    print("\n--- API config extraction ---")

    # Find window.__CONFIG or similar
    configs = re.findall(r'window\.__?\w+__?\s*=\s*(\{[^;]{10,5000}\})', html)
    for i, cfg in enumerate(configs):
        print(f"\nWindow config {i}: {cfg[:1000]}")

    # Find API endpoints in inline scripts
    api_patterns = re.findall(r'["\'](?:https?://[^"\']*(?:api|graphql|search|availability)[^"\']*)["\']', html, re.IGNORECASE)
    if api_patterns:
        print(f"\nAPI URLs in page:")
        for u in sorted(set(api_patterns)):
            print(f"  {u}")

    # Check for a /api/ proxy pattern (common in React apps)
    print("\n--- RA API endpoint probes ---")

    # The SPA likely calls these internally
    for path in [
        "/api/search",
        "/api/search/campgrounds",
        "/api/campgrounds",
        "/api/availability",
        "/api/facilities",
        "/api/explore",
        "/api/v1/search",
        "/api/v1/campgrounds",
    ]:
        r = probe(f"RA {path}", f"https://www.reserveamerica.com{path}",
                  extra_headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})

    # 2. Try the React SPA's internal search API
    # The SPA showed 'provider':{'contract':true,'web':true} — try contract-based search
    probe("RA search POST", "https://www.reserveamerica.com/api/search",
          method="POST", json_body={
              "contractCode": "OR",
              "stateCode": "OR",
              "category": "camping",
              "pageSize": 10
          })

    # 3. Try facility detail endpoint pattern seen in HTML
    # Pattern from HTML: /explore/{slug}/{state-code}/{parkId}/campsite-availability
    probe("RA Fort Stevens avail",
          "https://www.reserveamerica.com/explore/fort-stevens-state-park/OR/402178/campsite-availability")

    # 4. Try the campsite search endpoint (legacy but may still work behind the SPA)
    probe("RA campsiteSearch API",
          "https://www.reserveamerica.com/campsiteSearch.do?contractCode=OR&parkId=402178",
          extra_headers={"Accept": "application/json"})


if __name__ == "__main__":
    idaho_deep_probe()
    reserveamerica_spa_probe()
