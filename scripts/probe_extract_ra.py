"""
Extract availability data from the unified www.reserveamerica.com availability page.
The page is a Next.js SSR app with data embedded in __NEXT_DATA__ or window.__STATE__.
"""

import json
import re
from curl_cffi import requests as cffi_requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def main():
    url = "https://www.reserveamerica.com/explore/fort-stevens-state-park/OR/402178/campsite-availability"
    print(f"Fetching: {url}")
    resp = cffi_requests.get(url, headers=HEADERS, impersonate="chrome131", timeout=30)
    print(f"Status: {resp.status_code}, Size: {len(resp.text)} chars")

    html = resp.text

    # 1. Try __NEXT_DATA__
    match = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        print("\n=== __NEXT_DATA__ found ===")
        try:
            data = json.loads(match.group(1))
            # Save to file for analysis
            with open("data/ra_next_data_sample.json", "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved to data/ra_next_data_sample.json ({len(match.group(1))} chars)")

            # Explore the structure
            print(f"\nTop keys: {list(data.keys())}")
            if "props" in data:
                print(f"Props keys: {list(data['props'].keys())}")
                if "pageProps" in data["props"]:
                    pp = data["props"]["pageProps"]
                    print(f"PageProps keys: {list(pp.keys())}")
                    for k, v in pp.items():
                        v_str = json.dumps(v) if not isinstance(v, str) else v
                        print(f"  {k}: type={type(v).__name__}, size={len(v_str)}")
                        if isinstance(v, dict):
                            print(f"    keys: {list(v.keys())[:15]}")
                        elif isinstance(v, list) and len(v) > 0:
                            print(f"    len={len(v)}, first item keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__}")
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"First 500 chars: {match.group(1)[:500]}")
    else:
        print("No __NEXT_DATA__ found")

    # 2. Try window.__ patterns
    window_patterns = re.findall(r'window\.(__\w+__)\s*=\s*(\{.*?\});', html, re.DOTALL)
    for name, val in window_patterns:
        print(f"\n=== window.{name} ({len(val)} chars) ===")
        try:
            data = json.loads(val)
            print(f"Keys: {list(data.keys())[:20]}")
        except Exception:
            print(f"First 300: {val[:300]}")

    # 3. Find JSON-like objects containing availability data
    # Look for the resultsMap which was detected earlier
    results_match = re.search(r'"resultsMap"\s*:\s*(\{[^}]{100,})', html)
    if results_match:
        print(f"\n=== resultsMap found ===")
        # Try to extract a balanced JSON object
        text = results_match.group(1)
        print(f"First 500 chars: {text[:500]}")

    # 4. Look for siteAvail data pattern
    avail_matches = re.findall(r'"siteAvail(?:ability)?"\s*:\s*(\{[^}]{20,300}\})', html)
    if avail_matches:
        print(f"\n=== siteAvail patterns ({len(avail_matches)} matches) ===")
        for m in avail_matches[:5]:
            print(f"  {m[:200]}")

    # 5. Look for campsiteData or similar
    for pattern in [r'"campsites?"\s*:\s*\[', r'"sites?"\s*:\s*\[',
                    r'"units?"\s*:\s*\[', r'"inventory"\s*:\s*\{']:
        matches = list(re.finditer(pattern, html))
        if matches:
            for m in matches[:2]:
                start = m.start()
                print(f"\n=== Pattern '{pattern}' at pos {start} ===")
                print(f"  Context: ...{html[max(0,start-50):start+200]}...")


if __name__ == "__main__":
    main()
