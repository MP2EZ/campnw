import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useSearch, parseSearchParamsFromUrl } from "../hooks/useSearch";
import { searchCampsitesStream } from "../api";
import type { CampgroundResult, SearchParams } from "../api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

let capturedOnResult: ((r: CampgroundResult) => void) | null = null;
let capturedOnDone: (() => void) | null = null;
let capturedOnError: ((err: Error) => void) | null = null;
let capturedOnWarnings: ((w: unknown[]) => void) | null = null;

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
      // 5 onWarnings
      capturedOnWarnings = (rest[5] as ((w: unknown[]) => void)) ?? null;
    },
  ),
  saveSearchHistory: vi.fn(),
  track: vi.fn(),
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
