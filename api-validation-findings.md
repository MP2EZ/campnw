# API Validation Findings — 2026-03-21

Results from running `scripts/validate_apis.py` against all target data sources.

## Recreation.gov RIDB (Metadata)
- **Status: WORKING (with API key)**
- Key stored in `.env` as `RIDB_API_KEY`
- Returned **194 WA camping facilities** — more than enough for seeding the registry
- Not all 194 are campgrounds you'd want (e.g. "SWAN LAKE KITCHEN" came back) — will need filtering during import by facility type or activity
- Sample results: Beaver Campground (232864), Kaner Flat (251362), Lodgepole (234027), Sawmill Flat (234022)

## Recreation.gov Availability (Undocumented)
- **Status: WORKING — this is the critical one**
- Tested with Ohanapecosh Campground (facility_id=`232464`)
- Returned **151 campsites** for July 2026

### Verified response shape (build models to match this):
```json
{
  "campsites": {
    "2560": {
      "campsite_id": "2560",
      "site": "D016",
      "loop": "A-F",
      "campsite_type": "STANDARD NONELECTRIC",
      "type_of_use": "Overnight",
      "min_num_people": 0,
      "max_num_people": 8,
      "availabilities": {
        "2026-07-01T00:00:00Z": "NYR",
        "2026-07-02T00:00:00Z": "Reserved"
      }
    }
  }
}
```

### Key observations:
- `campsites` dict is keyed by campsite_id **as a string**
- Availability dates use ISO format with `T00:00:00Z` suffix
- July 2026 showed all `NYR` for the first 50 sites (reservations not yet open) but some sites in the full 151 had `Reserved` — the reservation window varies by campground
- First 50 sites: 0 Available, 1054 Reserved across all days — means the remaining ~100 sites were NYR
- Known statuses observed: `NYR`, `Reserved`. Brief also mentions `Available`, `Not Available`
- `min_num_people` can be 0 (not 1) — handle accordingly in search filters

## Recreation.gov Search API
- **Status: NOT WORKING as documented**
- `GET /api/search?q=camping&fq=state:WA&size=5&start=0` returned HTTP 200 but **0 results**
- The `fq` (filter query) parameter format may have changed
- Investigation needed: try without `fq`, try the `/api/search/suggest` endpoint, check camply's search patterns
- **Lower priority** — RIDB already covers campground discovery and the availability API is the main workhorse

## WA State Parks / GoingToCamp
- **Status: BLOCKED — all 3 endpoints return 403**
- All of `/api/maps`, `/api/resourcecategory`, `POST /api/availability/map` return 403
- The 403 response body is an **Azure WAF** block page (HTML with "Azure WAF" in the title)
- This is not a simple auth issue — it's bot detection at the CDN/WAF layer
- Approaches to investigate:
  - `cloudscraper` or `curl_cffi` (TLS fingerprint spoofing)
  - Playwright/headless browser to get session cookies, then use cookies with httpx
  - Check how camply's GoingToCamp provider handles this — may have a newer workaround
  - Tacoma Power (`tacomapower.goingtocamp.com`) may have looser WAF rules — worth testing

## Oregon State Parks / ReserveAmerica
- **Status: BLOCKED — 403**
- `oregonstateparks.reserveamerica.com` returned 403 with 118-byte HTML response
- Same bot protection pattern as GoingToCamp but different vendor
- Phase 4 stretch goal — will need Playwright

## Summary Table

| Source | Status | Auth | Priority |
|--------|--------|------|----------|
| RIDB metadata | Working | API key | Phase 1 |
| Rec.gov availability | Working | None (User-Agent only) | Phase 1 |
| Rec.gov search | 200 but 0 results | None | Low — investigate later |
| WA GoingToCamp | 403 Azure WAF | Needs bypass | Phase 2 |
| OR ReserveAmerica | 403 | Needs bypass | Phase 4 |

## Test Campground IDs (for development)
- Ohanapecosh: `232464` (Mt. Rainier NP, 151 sites)
- Cougar Rock: `232463` (Mt. Rainier NP)
