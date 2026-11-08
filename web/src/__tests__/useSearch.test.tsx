import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useSearch, parseSearchParamsFromUrl } from "../hooks/useSearch";
import { searchCampsitesStream, track, getPosthog } from "../api";
import type { CampgroundResult, SearchParams } from "../api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

let capturedOnResult: ((r: CampgroundResult) => void) | null = null;
let capturedOnDone: (() => void) | null = null;
let capturedOnError: ((err: Error) => void) | null = null;
let capturedOnWarnings: ((w: unknown[]) => void) | null = null;
let capturedOnDiagnosis: ((e: unknown) => void) | null = null;
let capturedOnNotReleased: ((s: unknown) => void) | null = null;
let capturedOnCoverage: ((matched: number, checked: number) => void) | null = null;
let capturedSignal: AbortSignal | null = null;

vi.mock("../api", () => ({
  searchCampsitesStream: vi.fn(
    async (
      _params: any,
      onResult: any,
      onDone: any,
      onError: any,
      ...rest: unknown[]
    ) => {
      capturedOnResult = onResult;
      capturedOnDone = onDone;
      capturedOnError = onError;
      // after (params, onResult, onDone, onError) the rest are:
      // 0 onDiagnosis, 1 signal, 2 onParsed, 3 onSummary, 4 onProgress,
      // 5 onWarnings, 6 onCoverage, 7 onNotReleased
      capturedOnDiagnosis = (rest[0] as ((e: unknown) => void)) ?? null;
      capturedSignal = (rest[1] as AbortSignal) ?? null;
      capturedOnWarnings = (rest[5] as ((w: unknown[]) => void)) ?? null;
      capturedOnCoverage =
        (rest[6] as ((matched: number, checked: number) => void)) ?? null;
      capturedOnNotReleased = (rest[7] as ((s: unknown) => void)) ?? null;
    },
  ),
  saveSearchHistory: vi.fn(),
  track: vi.fn(),
  getPosthog: vi.fn(() => ({ register: vi.fn(), capture: vi.fn() })),
}));

// Stub window methods used by useSearch
Object.defineProperty(window, "scrollTo", { value: vi.fn() });

// Make requestAnimationFrame synchronous so RAF-throttled state updates flush immediately
vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 0; });
vi.stubGlobal("cancelAnimationFrame", vi.fn());

const MOCK_RESULT: CampgroundResult = {
  facility_id: "232465",
  name: "Ohanapecosh",
  booking_system: "recgov",
  total_available_sites: 5,
  fcfs_sites: 0,
  windows: [],
  availability_url: "https://recreation.gov/camping/campgrounds/232465",
  estimated_drive_minutes: 150,
  tags: ["forest", "riverside"],
  elevator_pitch: null,
  vibe: null,
  description_rewrite: null,
  best_for: null,
  latitude: 46.75,
  longitude: -121.8,
} as any;

const MOCK_OR_RESULT: CampgroundResult = {
  ...MOCK_RESULT,
  facility_id: "409402",
  name: "Cape Lookout",
  booking_system: "or_state",
} as any;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSearch", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
    capturedOnResult = null;
    capturedOnDone = null;
    capturedOnError = null;
  });

  test("initial state: null results, not loading, no error", () => {
    const { result } = renderHook(() => useSearch(null));

    expect(result.current.results).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test("handleSearch sets loading and calls searchCampsitesStream", async () => {
    const { searchCampsitesStream } = await import("../api");
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    expect(searchCampsitesStream).toHaveBeenCalled();
  });

  test("streaming results accumulate via onResult callback", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    // Simulate SSE results arriving
    act(() => {
      capturedOnResult?.(MOCK_RESULT);
    });

    expect(result.current.results?.results).toHaveLength(1);
    expect(result.current.results?.results[0].name).toBe("Ohanapecosh");

    act(() => {
      capturedOnResult?.(MOCK_OR_RESULT);
    });

    expect(result.current.results?.results).toHaveLength(2);
  });

  test("onDone sets loading false", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    act(() => {
      capturedOnResult?.(MOCK_RESULT);
      capturedOnDone?.();
    });

    expect(result.current.loading).toBe(false);
  });

  test("onError sets error message", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    act(() => {
      capturedOnError?.(new Error("Network timeout"));
    });

    expect(result.current.error).toBe("Network timeout");
    expect(result.current.loading).toBe(false);
  });

  test("a superseded search's end or error doesn't settle the new one", async () => {
    const { result } = renderHook(() => useSearch(null));
    const search = () => act(async () => {
      result.current.handleSearch({ start_date: "2026-06-01", end_date: "2026-06-30" }, "find");
    });
    await search();
    const firstDone = capturedOnDone!;
    const firstError = capturedOnError!;
    await search();

    act(() => {
      firstDone();
      firstError(new Error("aborted late"));
    });
    expect(result.current.loading).toBe(true);
    expect(result.current.error).toBeNull();

    act(() => capturedOnDone?.());
    expect(result.current.loading).toBe(false);
  });

  test("resetSearch stops the running search", async () => {
    const { result } = renderHook(() => useSearch(null));
    await act(async () => {
      result.current.handleSearch({ start_date: "2026-06-01", end_date: "2026-06-30" }, "find");
    });
    act(() => result.current.resetSearch());
    expect(capturedSignal?.aborted).toBe(true);
    expect(result.current.loading).toBe(false);
  });

  test("a failed search forgets when the previous one finished", async () => {
    const { result } = renderHook(() => useSearch(null));
    const search = () => act(async () => {
      result.current.handleSearch({ start_date: "2026-06-01", end_date: "2026-06-30" }, "find");
    });
    await search();
    act(() => capturedOnDone?.());
    expect(result.current.completedAt).not.toBeNull();
    await search();
    act(() => capturedOnError?.(new Error("The search stopped responding")));
    expect(result.current.completedAt).toBeNull();
  });

  test("toggleSource: first click isolates, then clicks toggle on/off", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    act(() => {
      capturedOnResult?.(MOCK_RESULT);
      capturedOnResult?.(MOCK_OR_RESULT);
      capturedOnDone?.();
    });

    // Both sources active initially (default)
    expect(result.current.sourceFilter.has("recgov")).toBe(true);
    expect(result.current.sourceFilter.has("or_state")).toBe(true);

    // First click from "all on" isolates to that source
    act(() => result.current.toggleSource("recgov"));
    expect(result.current.sourceFilter.has("recgov")).toBe(true);
    expect(result.current.sourceFilter.has("or_state")).toBe(false);

    // Click another to add it (now both on again)
    act(() => result.current.toggleSource("or_state"));
    expect(result.current.sourceFilter.has("recgov")).toBe(true);
    expect(result.current.sourceFilter.has("or_state")).toBe(true);

    // Isolate again, then toggle the last one off — resets to all
    act(() => result.current.toggleSource("recgov")); // isolate to recgov
    act(() => result.current.toggleSource("recgov")); // remove last → reset
    expect(result.current.sourceFilter.has("recgov")).toBe(true);
    expect(result.current.sourceFilter.has("or_state")).toBe(true);
  });

  test("filteredResults respects source filter", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    act(() => {
      capturedOnResult?.(MOCK_RESULT);
      capturedOnResult?.(MOCK_OR_RESULT);
      capturedOnDone?.();
    });

    expect(result.current.filteredResults).toHaveLength(2);

    // Click isolates to recgov only
    act(() => result.current.toggleSource("recgov"));
    expect(result.current.filteredResults).toHaveLength(1);
    expect(result.current.filteredResults[0].name).toBe("Ohanapecosh");
  });

  test("formCollapsed is set to true after search", async () => {
    const { result } = renderHook(() => useSearch(null));
    expect(result.current.formCollapsed).toBe(false);

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" },
        "find",
      );
    });

    expect(result.current.formCollapsed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Provider degradation must reach state, not be hardcoded away (audit ANLT-06)
// ---------------------------------------------------------------------------

describe("useSearch provider warnings", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
    capturedOnResult = null;
    capturedOnDone = null;
    capturedOnError = null;
    capturedOnWarnings = null;
  });

  // Every setResults call passed `warnings: []`, so even once the stream
  // carried them they had nowhere to land. During the ReserveAmerica outage
  // (#131) an Oregon search just returned fewer results, with no explanation.
  test("a warnings frame lands in results.warnings", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" } as SearchParams,
        "find",
      );
    });

    expect(capturedOnWarnings).toBeTypeOf("function");

    await act(async () => {
      capturedOnWarnings?.([
        {
          kind: "waf_blocked",
          count: 2,
          source: "or_state",
          message: "Oregon State Parks results unavailable — the booking site is blocking requests.",
        },
      ]);
    });

    expect(result.current.results?.warnings).toHaveLength(1);
    expect(result.current.results?.warnings[0]).toMatchObject({
      source: "or_state",
      count: 2,
    });
  });

  test("warnings survive subsequent streamed results", async () => {
    const { result } = renderHook(() => useSearch(null));
    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" } as SearchParams,
        "find",
      );
    });

    await act(async () => {
      capturedOnWarnings?.([
        { kind: "waf_blocked", count: 1, source: "or_state", message: "x" },
      ]);
    });
    await act(async () => {
      capturedOnResult?.(MOCK_RESULT);
    });

    expect(result.current.results?.warnings).toHaveLength(1);
  });
})

describe("useSearch end-of-stream frames", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
  });

  async function startSearch() {
    const hook = renderHook(() => useSearch(null));
    await act(async () => {
      hook.result.current.handleSearch(
        { start_date: "2027-06-04", end_date: "2027-06-27" } as SearchParams,
        "find",
      );
    });
    return hook;
  }

  // The diagnosis frame arrives just before [DONE], and onDone rebuilt
  // `results` from scratch, so the zero-results screen never saw it.
  test("the diagnosis survives the end of the stream", async () => {
    const { result } = await startSearch();
    await act(async () => {
      capturedOnDiagnosis?.({
        type: "diagnosis",
        diagnosis: {
          registry_matches: 40, distance_filtered: 0, checked_for_availability: 20,
          binding_constraint: "not_released", explanation: "18 of 20 campgrounds…",
        },
        date_suggestions: [],
        action_chips: [{ action: "watch", label: "Set a watch", params: {} }],
      });
    });
    await act(async () => capturedOnDone?.());

    expect(result.current.results?.diagnosis?.binding_constraint).toBe("not_released");
    expect(result.current.results?.action_chips).toHaveLength(1);
  });

  test("a not_released frame lands in results and survives the end", async () => {
    const { result } = await startSearch();
    await act(async () => {
      capturedOnNotReleased?.({
        type: "not_released",
        not_released_campgrounds: 18,
        releases_on_earliest: "2026-12-04",
        releases_on_latest: "2026-12-25",
      });
    });
    await act(async () => capturedOnResult?.(MOCK_RESULT));
    await act(async () => capturedOnDone?.());

    expect(result.current.results).toMatchObject({
      not_released_campgrounds: 18,
      releases_on_earliest: "2026-12-04",
      releases_on_latest: "2026-12-25",
    });
  });
});

// ---------------------------------------------------------------------------
// Regression: sourceFilter must bail out when the source set is unchanged
// (audit PERF-07)
// ---------------------------------------------------------------------------

describe("useSearch sourceFilter identity", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
    capturedOnResult = null;
    capturedOnDone = null;
    capturedOnError = null;
  });

  // `resultSources` is a useMemo returning `new Set(...)` — a fresh reference
  // every time it recomputes. An unconditional setSourceFilter(resultSources)
  // therefore never bails out, so each streamed result produced a second full
  // render pass on top of the one setResults already caused. During a
  // streaming search that runs once per animation frame, doubling the render
  // cost of the whole results tree for the duration of the search.
  test("streaming further results from the same source does not keep replacing the filter", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" } as SearchParams,
        "find",
      );
    });

    await act(async () => {
      capturedOnResult?.(MOCK_RESULT);
    });
    const filterAfterFirst = result.current.sourceFilter;

    // Two more results from the *same* booking_system — the set of distinct
    // sources is unchanged, so the filter object should be too.
    await act(async () => {
      capturedOnResult?.({ ...MOCK_RESULT, facility_id: "2" });
    });
    await act(async () => {
      capturedOnResult?.({ ...MOCK_RESULT, facility_id: "3" });
    });

    expect(result.current.sourceFilter).toBe(filterAfterFirst);
  });

  test("a genuinely new source still updates the filter", async () => {
    const { result } = renderHook(() => useSearch(null));

    await act(async () => {
      result.current.handleSearch(
        { start_date: "2026-06-01", end_date: "2026-06-30" } as SearchParams,
        "find",
      );
    });

    await act(async () => {
      capturedOnResult?.(MOCK_RESULT);
    });
    const filterAfterFirst = result.current.sourceFilter;

    await act(async () => {
      capturedOnResult?.(MOCK_OR_RESULT);
    });

    expect(result.current.sourceFilter).not.toBe(filterAfterFirst);
    expect(result.current.sourceFilter.has("or_state")).toBe(true);
    expect(result.current.sourceFilter.has("recgov")).toBe(true);
  });
})

// ---------------------------------------------------------------------------
// URL round-trip: params were written but never read back (audit UX-03)
// ---------------------------------------------------------------------------

describe("parseSearchParamsFromUrl", () => {
  test("returns null without a usable date range", () => {
    expect(parseSearchParamsFromUrl("")).toBeNull();
    expect(parseSearchParamsFromUrl("?state=WA")).toBeNull();
    expect(parseSearchParamsFromUrl("?start_date=2026-06-01")).toBeNull();
    expect(parseSearchParamsFromUrl("?start_date=nope&end_date=2026-06-30")).toBeNull();
  });

  test("round-trips the params handleSearch writes", () => {
    const parsed = parseSearchParamsFromUrl(
      "?start_date=2026-06-01&end_date=2026-06-30&state=WA&nights=2" +
        "&tags=lakeside,pets&days_of_week=4,5,6&from_location=seattle" +
        "&max_drive=180&mode=find&no_groups=true",
    );
    expect(parsed).toEqual({
      start_date: "2026-06-01",
      end_date: "2026-06-30",
      state: "WA",
      nights: 2,
      tags: "lakeside,pets",
      days_of_week: "4,5,6",
      from_location: "seattle",
      max_drive: 180,
      mode: "find",
      no_groups: true,
    });
  });

  test("omits absent keys rather than emitting undefined", () => {
    const parsed = parseSearchParamsFromUrl(
      "?start_date=2026-06-01&end_date=2026-06-30",
    );
    expect(Object.keys(parsed!).sort()).toEqual(["end_date", "start_date"]);
  });

  test("ignores non-numeric numbers instead of producing NaN", () => {
    const parsed = parseSearchParamsFromUrl(
      "?start_date=2026-06-01&end_date=2026-06-30&nights=abc&max_drive=xyz",
    );
    expect(parsed).not.toHaveProperty("nights");
    expect(parsed).not.toHaveProperty("max_drive");
  });
});

describe("useSearch URL restore", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
    capturedOnResult = null;
    capturedOnDone = null;
    capturedOnError = null;
  });

  test("a shared link runs its search on mount", async () => {
    window.history.replaceState(
      null, "", "/?start_date=2026-06-01&end_date=2026-06-30&state=WA",
    );

    const { result } = renderHook(() => useSearch(null));

    // Previously nothing read the URL back, so a pasted link showed a blank
    // first-visit form and never searched.
    await waitFor(() =>
      expect(vi.mocked(searchCampsitesStream)).toHaveBeenCalled(),
    );
    expect(vi.mocked(searchCampsitesStream).mock.calls[0][0]).toMatchObject({
      start_date: "2026-06-01",
      end_date: "2026-06-30",
      state: "WA",
    });
    // SearchForm reads initialValues once during useState init, so the params
    // must already be present on the first render.
    expect(result.current.activeSearchParams).toMatchObject({ state: "WA" });
  });

  test("restores only once", async () => {
    window.history.replaceState(
      null, "", "/?start_date=2026-06-01&end_date=2026-06-30",
    );
    const { rerender } = renderHook(() => useSearch(null));
    await waitFor(() =>
      expect(vi.mocked(searchCampsitesStream)).toHaveBeenCalledTimes(1),
    );
    rerender();
    rerender();
    expect(vi.mocked(searchCampsitesStream)).toHaveBeenCalledTimes(1);
  });

  test("a bare URL does not trigger a search", async () => {
    renderHook(() => useSearch(null));
    await new Promise((r) => setTimeout(r, 20));
    expect(vi.mocked(searchCampsitesStream)).not.toHaveBeenCalled();
  });
})

// ---------------------------------------------------------------------------
// Search funnel instrumentation (audit ANLT-06 remainder, ANLT-07)
// ---------------------------------------------------------------------------

describe("useSearch funnel events", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
    capturedOnResult = null;
    capturedOnDone = null;
    capturedOnError = null;
  });

  async function runSearch(hook: {
    result: { current: { handleSearch: (p: SearchParams, m: "find" | "exact") => void } };
  }) {
    await act(async () => {
      hook.result.current.handleSearch(
        {
          start_date: "2026-06-01",
          end_date: "2026-06-08",
          state: "WA",
          tags: "lakeside,pets",
          max_drive: 180,
        } as SearchParams,
        "find",
      );
    });
  }

  // search_executed carried four props, so a zero-result search was countable
  // but not diagnosable: the dimensions that *cause* one — dates, lead time,
  // radius, tags — all sat unused in `params`.
  test("search_executed carries the dimensions that explain a zero result", async () => {
    const hook = renderHook(() => useSearch(null));
    await runSearch(hook);
    await act(async () => {
      capturedOnDone?.();
    });

    const call = vi.mocked(track).mock.calls.find((c) => c[0] === "search_executed");
    expect(call).toBeDefined();
    expect(call![1]).toMatchObject({
      state: "WA",
      date_range_days: 7,
      radius_minutes: 180,
      tag_count: 2,
      mode: "find",
    });
    expect(call![1].search_id).toBeTruthy();
  });

  // A failed search emitted nothing at all, so it was indistinguishable from a
  // search that was never run.
  test("a failed search emits search_failed", async () => {
    const hook = renderHook(() => useSearch(null));
    await runSearch(hook);
    await act(async () => {
      capturedOnError?.(new Error("stream died"));
    });

    const call = vi.mocked(track).mock.calls.find((c) => c[0] === "search_failed");
    expect(call).toBeDefined();
    expect(call![1]).toMatchObject({ reason: "stream died", state: "WA" });
  });

  test("search_id is registered as a super property for downstream events", async () => {
    const hook = renderHook(() => useSearch(null));
    await runSearch(hook);
    const ph = vi.mocked(getPosthog).mock.results[0]?.value;
    expect(ph.register).toHaveBeenCalledWith(
      expect.objectContaining({ search_id: expect.any(String) }),
    );
  });
})

describe("useSearch coverage", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.clearAllMocks();
  });

  const PARAMS = { start_date: "2026-06-01", end_date: "2026-06-30" } as SearchParams;

  test("a coverage frame lands in results and survives later flushes", async () => {
    const { result } = renderHook(() => useSearch(null));
    await act(async () => {
      result.current.handleSearch(PARAMS, "find");
    });
    expect(result.current.results?.campgrounds_matched).toBeUndefined();

    await act(async () => {
      capturedOnCoverage?.(46, 20);
    });
    expect(result.current.results).toMatchObject({
      campgrounds_matched: 46, campgrounds_checked: 20,
    });

    await act(async () => {
      capturedOnResult?.(MOCK_RESULT);
      capturedOnDone?.();
    });
    expect(result.current.results?.campgrounds_matched).toBe(46);
  });

  test("checkRest re-runs the same search with the higher limit", async () => {
    const { searchCampsitesStream } = await import("../api");
    const { result } = renderHook(() => useSearch(null));
    await act(async () => {
      result.current.handleSearch({ ...PARAMS, state: "WA", limit: 20 }, "exact");
    });
    await act(async () => {
      result.current.checkRest(46);
    });

    const calls = vi.mocked(searchCampsitesStream).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[1][0]).toMatchObject({ ...PARAMS, state: "WA", limit: 46 });
    expect(result.current.maxResults).toBe(46);
  });
});
