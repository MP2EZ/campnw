# Bloat cleanup — plan

Source: `/m:audit . --bloat` on 2026-11-16, 214 findings (2 critical, 98 warning, 114 info).
Full findings: `/Users/max/dev/pnw-campsite-tool/.audit-run/report.md` (untracked; worktrees read it by absolute path).

## Approach

- Packages own **files**, not findings, so agents in parallel worktrees never edit the same file. A finding that spans packages is split by file; the package listed first owns the signature change and its call sites.
- **Wave 1** = source packages (they also fix any test their change breaks). **Wave 2** = test-only and cross-cutting packages, branched from `dev` after wave 1 merges.
- Each agent **verifies every finding before acting** (findings are model claims; expect some to be wrong) and reports skipped ones with the reason.
- Branch per package `chore/bloat-<pkg>` off `dev`, conventional commits under 400 LOC each, one PR per package to `dev`. A package whose diff runs past ~400 lines is split into two PRs.
- Agents: Sonnet in isolated worktrees (mechanical work to spec). Behavior changes are written into the brief as exact specs. I review every diff before its PR goes up.
- Gate per package: `ruff check`, the affected `pytest` files, and `npx tsc --noEmit && npx vitest run` for web packages. Gate at the end: the full pytest + vitest suites on `dev`.

## Sweep rules (every package applies these within its own files)

- S1 Hoist function-local imports that have no cycle or startup-cost reason; drop duplicate imports.
- S2 Delete comments that restate the next line, narrate history ("previously…", "used to…"), or cite tickets/plan IDs (PERF-01, v1.48 P3a, slice 4a). Keep one-line WHY comments.
- S3 (tests) Use the shared conftest `make_campground`, `registry`, `watch_db` and `signup_and_auth` instead of local copies. Drop redundant `@pytest.mark.asyncio` (`asyncio_mode = "auto"`).
- S4 (tests) Delete tests that restate a constant, test the mock or the framework, or duplicate a sibling test. Fix tests that cannot fail (guards around their only assertion, `>= 0`, `<= N` that `[]` satisfies) so they assert the real behavior.

## Wave 1 — source packages (7 agents in parallel)

| Pkg | Owns | Findings |
|---|---|---|
| **B1 API & routes** | `api.py`, `routes/*` except `planner.py`, `analytics/*` | 02 (delete `/api/compare` + `test_compare.py`), 03, 07, 10, 20, 21, 30, 44, 64, 75, 76, 77 (scheduler side), 91, 110, 111, 112, 128, 129 (api.py part), 143, 144, 169, 174/199 (their files) |
| **B2 Search & providers** | `search/*`, `providers/*` | 18, 19, 22, 31, 113, 122 (engine part), 142, 175, 200 |
| **B3 Monitor & registry** | `monitor/*`, `registry/*`, `health.py`, `auth.py`, `posthog_client.py` | 04, 05, 09, 17 (+ its one call site in `routes/watches.py`), 77 (delete the other dead DB methods), 102, 107, 129, 140, 171, 173, 197, 198, 213 |
| **B4 Planner, enrichment, CLI** | `planner/*`, `routes/planner.py`, `enrichment/*`, `__main__.py` | 06, 28, 29, 43, 78, 90, 100, 103, 104, 109, 121, 122 (agent part), 127, 139, 141, 172 (add `source` to the `search_campgrounds` schema), 174/199 (their files) |
| **B5 Scripts, docs, iOS** | `scripts/*`, `docs/*.html`, `start.sh`, `web/ios/App/App/AppDelegate.swift` | 15, 16, 57, 74, 88, 89, 97, 101, 166, 167, 168, 194, 195, 196, 211, 212 |
| **F1 Web results & lib** | `web/src/results/*`, `web/src/lib/*`, `App.tsx`, `main.tsx` | 61, 62, 72, 86, 95, 105, 125, 135, 153, 162, 163, 165, 191, 192, 205, 210 |
| **F2 Web API, hooks, components, pages** | `web/src/api.ts`, `hooks/*`, `components/*`, `pages/*` | 01, 27, 59, 60, 85, 106, 120, 158, 159, 160, 161, 164, 188, 189, 190, 209 (return focus to the opener when WatchPanel closes) |

## Wave 2 — tests and cross-cutting (4 agents in parallel, after wave 1 merges)

| Pkg | Owns | Findings |
|---|---|---|
| **T1 Python tests: search, registry, API** | `tests/conftest.py`, `test_search*`, `test_registry*`, `test_geo*`, `test_urls`, `test_nl_parser`, `test_api_*`, `test_audit_gaps`, `test_drive_times_db`, `test_seo*`, `test_release_*`, `test_tag_*`, `test_seed_filter`, `test_availability_cache`, `test_perf_hot_paths`, `test_history_compact`, `test_stream_warnings`, `test_mapbox`, `test_oregon_deadline` | 08, 13, 14, 23, 26, 32, 34, 35, 36, 40, 46, 51, 54, 55, 65 (its files), 66, 70, 81, 84, 92, 93, 98, 114, 115, 117, 118, 119, 123, 124, 130, 132, 133, 137, 145, 146, 148, 151, 152, 177, 178, 179, 182, 183, 202, 203, 204, 214 |
| **T2 Python tests: everything else** | all other `tests/*.py` | 11, 12, 24, 25, 33, 37, 38, 39, 47, 48, 49, 50, 52, 53, 56, 63, 65 (its files), 67, 68, 69, 79, 80, 82, 83, 96, 108, 116, 131, 136, 147, 149, 150, 176, 180, 181, 184, 185, 193, 201 |
| **W Web tests & e2e** | `web/src/__tests__/*`, `e2e/*` | 41, 58, 71, 73, 99, 126, 134, 138, 154, 155, 156, 157, 186, 187, 206, 207, 208 |
| **X Cross-cutting** | edits named in each finding | 45 (`or_state_availability_url` drops `end_date` and all call sites), 87 (one home-base list per language), 170 (one drive-time formatter per language) |

## Decisions (agreed 2026-11-16)

- **Delete:** the search summary (64), the notification-quality report (75), the non-streaming planner (`chat()`, `POST /api/plan/chat`, web `planChat()`; 78) and the truncation tooling (100).
- **Booking tips (76):** keep the pipeline (`analytics/patterns.py`, `registry.update_booking_tips`, the SEO profile section). Delete only the unused `GET /api/campgrounds/{id}/booking-tips` route. Scheduling it is a separate task: dry-run against prod data and review the output first.
- **Share links (77):** keep `cleanup_expired_links` and register it as a daily APScheduler job. Delete the other dead DB methods named in 77.
- **Zero-results reminders button (86):** wire it to open WatchSheet in remind mode, as `FullGroup` does.
- **Legacy `/map` (94):** keep the page. Remove only its dead `PIN_COLOR_FALLBACKS` (85).
- **`handoff/` (42):** untracked and local, so leave it alone.

## Not in scope

- `data/registry.db`, `project.pbxproj` and the other untracked files already in the `dev` working tree are left alone.
- iOS: removing the AppDelegate stubs (57) ships with the next TestFlight build. No rebuild is required for this work.
