import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSearch } from "../hooks/useSearch";
import type { CampgroundResult } from "../api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

let capturedOnResult: ((r: CampgroundResult) => void) | null = null;
let capturedOnDone: (() => void) | null = null;
let capturedOnError: ((err: Error) => void) | null = null;

vi.mock("../api", () => ({
  searchCampsitesStream: vi.fn(
    async (
      _params: any,
      onResult: any,
      onDone: any,
      onError: any,
    ) => {
      capturedOnResult = onResult;
      capturedOnDone = onDone;
      capturedOnError = onError;
    },
  ),
  saveSearchHistory: vi.fn(),
  track: vi.fn(),
}));

// Stub window methods used by useSearch
Object.defineProperty(window, "scrollTo", { value: vi.fn() });

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
