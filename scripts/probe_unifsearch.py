"""
Probe the ReserveAmerica unifSearchInterface.do endpoint.
This is an embeddable widget API found in the SPA source — may bypass WAF.

Key interfaces discovered:
- campavdetails: campsite availability details
- bookdailyentry: daily entry booking

Oregon endpoint: oregonstateparks.reserveamerica.com/unifSearchInterface.do
"""

import json
import re
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html, application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

OR_BASE = "https://oregonstateparks.reserveamerica.com"

# Known Oregon park IDs
PARKS = {
    "Fort Stevens": "402178",
    "Silver Falls": "402235",
    "Cape Lookout": "402146",
    "Nehalem Bay": "402191",
    "South Beach": "402165",
    "Found in SPA": "412354",  # from the SPA source
}


def probe(label, url, extra_headers=None):
    hdrs = {**HEADERS, **(extra_headers or {})}
    print(f"\n{'='*60}")
    print(f"[{label}] {url[:100]}")
    try:
        resp = cffi_requests.get(url, headers=hdrs, impersonate="chrome131",
                                  timeout=15, allow_redirects=True)
        print(f"Status: {resp.status_code} | Size: {len(resp.content)}b | CT: {resp.headers.get('content-type','')[:50]}")
        if resp.url != url:
            print(f"→ Redirected: {resp.url[:100]}")

        ct = resp.headers.get("content-type", "")
        text = resp.text

        if resp.status_code == 403:
            print(f"  BLOCKED — {text[:200]}")
            return resp

        if "json" in ct:
            try:
                data = resp.json()
                print(json.dumps(data, indent=2)[:3000])
            except Exception:
                print(text[:2000])
        elif "html" in ct:
            # Check if it's a real page or WAF block
            title = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
            if title:
                print(f"  Title: {title.group(1).strip()}")

            # Look for availability data patterns
            for pat in ["Available", "Reserved", "siteListLabel", "availstatus",
                        "siteavail", "campsite", "site_type", "bookingDate",
                        "calendarCell", "status_a", "status_r", "status_c"]:
                count = text.lower().count(pat.lower())
                if count > 0:
                    idx = text.lower().find(pat.lower())
                    snippet = text[max(0, idx-30):idx+80].replace('\n', ' ').strip()
                    print(f"  '{pat}' x{count}: ...{snippet}...")

            # Look for JSON embedded in page
            json_blocks = re.findall(r'<script[^>]*>\s*var\s+\w+\s*=\s*(\{[^;]{50,}?\});', text)
            for jb in json_blocks[:3]:
                print(f"  Inline JSON: {jb[:300]}")

            # Check for iframe/widget content (unifSearchInterface returns embeddable HTML)
            if len(text) < 50000:  # Small enough to be a widget
                # Look for campsite data
                sites = re.findall(r'(?:site|campsite|unit)\s*(?:name|id|number|#)\s*[:\-=]\s*["\']?(\w+)', text, re.IGNORECASE)
                if sites:
                    print(f"  Sites found: {sites[:20]}")

                avail = re.findall(r'(?:class|status|data-status)=["\']([^"\']*(?:avail|reserv|open|close)[^"\']*)["\']', text, re.IGNORECASE)
                if avail:
                    print(f"  Availability classes: {set(avail)}")

        return resp
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return None


def main():
    print("="*60)
    print("RESERVE AMERICA unifSearchInterface.do PROBE")
    print("="*60)

    # 1. Test the campavdetails interface for Oregon parks
    print("\n\n>>> unifSearchInterface campavdetails <<<\n")
    for name, park_id in PARKS.items():
        probe(f"campavdetails: {name}",
              f"{OR_BASE}/unifSearchInterface.do?interface=campavdetails&contractCode=OR&parkId={park_id}")

    # 2. Test other known interfaces
    print("\n\n>>> Other unifSearch interfaces <<<\n")
    for interface in ["campavdetails", "campground", "campgrnddetails",
                      "campsearch", "campmap", "facilitysearch",
                      "campgroundList", "availGrid"]:
        probe(f"interface={interface}",
              f"{OR_BASE}/unifSearchInterface.do?interface={interface}&contractCode=OR&parkId=402178")

    # 3. Try the specific state subdomain directly (non-widget)
    print("\n\n>>> Direct state subdomain (non-widget) <<<\n")

    # Try with Referer header (widget embeds have a referrer)
    probe("With Referer",
          f"{OR_BASE}/unifSearchInterface.do?interface=campavdetails&contractCode=OR&parkId=402178",
          extra_headers={"Referer": "https://stateparks.oregon.gov/"})

    # Try the direct campground details page
    probe("facilityDetails.do",
          f"{OR_BASE}/camping/fort-stevens-state-park/r/campgroundDetails.do?contractCode=OR&parkId=402178")

    # 4. Check if Idaho still has a working RA subdomain
    print("\n\n>>> Idaho RA subdomain check <<<\n")
    probe("Idaho RA homepage", "https://idahostateparks.reserveamerica.com")
    probe("Idaho RA POS", "https://idahostateparks.reserveamerica.com/pos.page")
    probe("Idaho RA unifSearch",
          "https://idahostateparks.reserveamerica.com/unifSearchInterface.do?interface=campavdetails&contractCode=ID")

    # 5. Try the unified www.reserveamerica.com availability page for Fort Stevens
    # (this loaded a 2.5MB page — check if it has actual availability data)
    print("\n\n>>> Unified RA availability page extraction <<<\n")
    resp = probe("RA unified: Fort Stevens avail",
                 "https://www.reserveamerica.com/explore/fort-stevens-state-park/OR/402178/campsite-availability")
    if resp and resp.status_code == 200:
        text = resp.text
        # Look for SSR'd availability data
        next_data = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', text)
        if next_data:
            try:
                data = json.loads(next_data.group(1))
                # Look for availability in the props
                props_str = json.dumps(data.get("props", {}))
                if "avail" in props_str.lower():
                    # Find the availability section
                    for key in ["pageProps", "initialProps", "dehydratedState"]:
                        if key in data.get("props", {}):
                            section = data["props"][key]
                            section_str = json.dumps(section)
                            if len(section_str) > 100:
                                print(f"\n  __NEXT_DATA__.props.{key} ({len(section_str)} chars):")
                                print(f"  Keys: {list(section.keys()) if isinstance(section, dict) else 'array'}")
                                if isinstance(section, dict):
                                    for k, v in section.items():
                                        v_str = json.dumps(v) if not isinstance(v, str) else v
                                        print(f"    {k}: {v_str[:200]}")
                else:
                    print(f"\n  __NEXT_DATA__ found but no availability data in props")
                    print(f"  Top-level keys: {list(data.keys())}")
                    if "props" in data:
                        print(f"  Props keys: {list(data['props'].keys())}")
            except json.JSONDecodeError:
                print(f"  __NEXT_DATA__ parse failed: {next_data.group(1)[:200]}")

        # Check for availability data in other script tags
        avail_scripts = re.findall(r'window\._(?:availability|campsite|facility)\s*=\s*(\{.+?\});', text)
        if avail_scripts:
            for a in avail_scripts:
                print(f"\n  Availability data: {a[:500]}")


if __name__ == "__main__":
    main()
