/**
 * useSearch — encapsulates all search state and orchestration logic.
 *
 * Extracted from App.tsx to reduce the god-file problem. Contains:
 * - Search results, loading, error state
 * - SSE stream orchestration (handleSearch)
 * - Source filter toggling
 * - Form collapse state
 * - Focused card + live announcement state
 * - Derived computations (filteredResults, resultSources)
 */

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { getPosthog, searchCampsitesStream, saveSearchHistory, track } from "../api";
import type {
  CampgroundResult, SearchParams, SearchResponse, SearchWarning,
  DiagnosisEvent,
} from "../api";

/**
 * Read a SearchParams back out of the query string.
 *
 * handleSearch has always *written* every param to the URL, so the address bar
 * looked shareable — but nothing anywhere read it back. A pasted or bookmarked
 * search link opened a blank first-visit form, and MapView's own "Edit search"
 * link built `/?state=WA&start_date=...` and then discarded all of it. Both
 * /pricing and /terms advertise shareable searches as a shipped feature.
 *
 * Returns null unless a usable date range is present, since that is the
 * minimum a search needs.
 */
export function parseSearchParamsFromUrl(
  search: string = window.location.search,
): SearchParams | null {
  const q = new URLSearchParams(search);
  const start = q.get("start_date") ?? "";
  const end = q.get("end_date") ?? "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return null;
  }

  const num = (key: string): number | undefined => {
    const raw = q.get(key);
    if (raw === null) return undefined;
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  };
  const str = (key: string): string | undefined => q.get(key) ?? undefined;

  const params: SearchParams = { start_date: start, end_date: end };
  const assign = <K extends keyof SearchParams>(k: K, v: SearchParams[K]) => {
    if (v !== undefined) params[k] = v;
  };

  assign("q", str("q"));
  assign("state", str("state"));
  assign("nights", num("nights"));
  assign("days_of_week", str("days_of_week"));
  assign("tags", str("tags"));
  assign("name", str("name"));
  assign("source", str("source"));
  assign("from_location", str("from_location"));
  assign("max_drive", num("max_drive"));
  assign("mode", str("mode"));
  assign("limit", num("limit"));
  if (q.get("no_groups") === "true") params.no_groups = true;
  if (q.get("include_fcfs") === "true") params.include_fcfs = true;

  return params;
}

/** Days between a search's start and end date; 0 when either is absent. */
function dateRangeDays(params: SearchParams): number {
  if (!params.start_date || !params.end_date) return 0;
  const a = Date.parse(params.start_date + "T12:00:00");
  const b = Date.parse(params.end_date + "T12:00:00");
  if (Number.isNaN(a) || Number.isNaN(b)) return 0;
  return Math.round((b - a) / 86_400_000);
}

/** Days from today to the search's start — how far ahead people plan. */
function leadTimeDays(params: SearchParams): number {
  if (!params.start_date) return 0;
  const start = Date.parse(params.start_date + "T12:00:00");
  if (Number.isNaN(start)) return 0;
  return Math.max(0, Math.round((start - Date.now()) / 86_400_000));
}

export type SearchMode = "find" | "exact";
export type ResultsView = "dates" | "sites";

export interface UserData {
  id: number;
  email: string;
  display_name: string;
  default_state: string;
  default_nights: number;
  default_from: string;
  recommendations_enabled: boolean;
}

export interface UseSearchReturn {
  results: SearchResponse | null;
  searchSummary: string | null;
  setSearchSummary: React.Dispatch<React.SetStateAction<string | null>>;
  loading: boolean;
  error: string | null;
  resultsView: ResultsView;
  setResultsView: (v: ResultsView) => void;
  searchDates: { start: string; end: string } | null;
  sourceFilter: Set<string>;
  resultSources: Set<string>;
  filteredResults: CampgroundResult[];
  activeSearchParams: SearchParams | null;
  searchId: string;
  formCollapsed: boolean;
  setFormCollapsed: (v: boolean) => void;
  focusedCardIndex: number;
  setFocusedCardIndex: React.Dispatch<React.SetStateAction<number>>;
  liveAnnouncement: string;
  setLiveAnnouncement: (s: string) => void;
  cardRefs: React.MutableRefObject<(HTMLButtonElement | null)[]>;
  maxResults: number;
  handleSearch: (params: SearchParams, mode: SearchMode) => Promise<void>;
  toggleSource: (src: string) => void;
  resetSearch: () => void;
}

export function useSearch(user: UserData | null): UseSearchReturn {
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [searchSummary, setSearchSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultsView, setResultsView] = useState<ResultsView>("dates");
  const [searchDates, setSearchDates] = useState<{ start: string; end: string } | null>(null);
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set());
  // Seeded from the URL so SearchForm's initialValues (which are read once,
  // during useState initialization) already reflect a shared link.
  const [activeSearchParams, setActiveSearchParams] = useState<SearchParams | null>(
    () => parseSearchParamsFromUrl(),
  );
  const [formCollapsed, setFormCollapsed] = useState(false);
  const [focusedCardIndex, setFocusedCardIndex] = useState(-1);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const lastSearchParams = useRef<SearchParams | null>(null);
  const lastSearchMode = useRef<SearchMode>("find");
  const searchAbortRef = useRef<AbortController | null>(null);
  // Correlates search_executed with the book_click / zero-state events it
  // produces. Exposed so ResultCard can stamp outbound clicks with it.
  const searchIdRef = useRef<string>("");

  const maxResults = lastSearchParams.current?.limit || 20;

  const resultSources = useMemo(() => {
    if (!results) return new Set<string>();
    return new Set(results.results.map((r) => r.booking_system));
  }, [results]);

  useEffect(() => {
    if (resultSources.size === 0) return;
    // resultSources is a fresh Set on every render, so an unconditional
    // setSourceFilter never bails out — during a streaming search, where
    // setResults fires once per animation frame, that produced *two* full
    // App-tree renders per frame instead of one. Compare contents, not
    // identity, and keep the previous Set when nothing actually changed.
    setSourceFilter((prev) =>
      prev.size === resultSources.size &&
      [...resultSources].every((s) => prev.has(s))
        ? prev
        : resultSources
    );
  }, [resultSources]);

  const filteredResults = useMemo(() => {
    if (!results) return [];
    return results.results
      .filter((r) => sourceFilter.has(r.booking_system))
      .slice(0, maxResults);
  }, [results, sourceFilter, maxResults]);

  useEffect(() => {
    setFocusedCardIndex(-1);
  }, [filteredResults]);

  const toggleSource = useCallback((src: string) => {
    setSourceFilter((prev) => {
      const allActive = prev.size === resultSources.size;
      if (allActive) {
        track("source_filter_changed", { source: src, action: "isolate", active_count: 1 });
        return new Set([src]);
      }
      const next = new Set(prev);
      if (next.has(src)) {
        next.delete(src);
      } else {
        next.add(src);
      }
      if (next.size === 0 || next.size === resultSources.size) {
        track("source_filter_changed", { source: src, action: "reset", active_count: resultSources.size });
        return new Set(resultSources);
      }
      track("source_filter_changed", {
        source: src,
        action: prev.has(src) ? "remove" : "add",
        active_count: next.size,
      });
      return next;
    });
  }, [resultSources]);

  const handleSearch = useCallback(async (params: SearchParams, mode: SearchMode) => {
    const searchParams = { ...params };
    lastSearchParams.current = params;
    lastSearchMode.current = mode;
    setActiveSearchParams(params);

    searchAbortRef.current?.abort();
    const abortController = new AbortController();
    searchAbortRef.current = abortController;
    searchIdRef.current =
      globalThis.crypto?.randomUUID?.() ?? String(Date.now());
    const searchId = searchIdRef.current;
    const startedAt = performance.now();
    // Super property rather than a prop: book_click fires from four nested
    // components inside ResultCard, and threading search_id to each of them
    // would be more invasive than the correlation is worth.
    getPosthog()?.register({ search_id: searchId });

    setLoading(true);
    setError(null);
    setSearchSummary(null);
    setResultsView(mode === "find" ? "dates" : "sites");
    if (params.start_date && params.end_date) {
      setSearchDates({ start: params.start_date, end: params.end_date });
    }
    setFormCollapsed(true);

    setTimeout(() => {
      document.querySelector(".results-skeleton, .results")?.scrollIntoView({
        behavior: "smooth", block: "start",
      });
    }, 100);

    const url = new URL(window.location.href);
    url.search = "";
    for (const [k, v] of Object.entries(searchParams)) {
      if (v !== undefined && v !== "" && v !== false) {
        url.searchParams.set(k, String(v));
      }
    }
    // pushState, not replaceState: with replace, Back never undid a search —
    // it left the site entirely.
    if (url.toString() !== window.location.href) {
      window.history.pushState(null, "", url.toString());
    }

    const streamedResults: CampgroundResult[] = [];
    // Warnings arrive as their own SSE frame near the end of the stream. They
    // were hardcoded to [] at every setResults call, so provider outages
    // reached the UI as silently fewer results.
    let streamedWarnings: SearchWarning[] = [];
    let rafId: number | null = null;
    let checkedCount = 0;
    setResults({
      campgrounds_checked: 0,
      campgrounds_with_availability: 0,
      results: [],
      warnings: [],
    });

    await searchCampsitesStream(
      searchParams,
      (result) => {
        streamedResults.push(result);
        checkedCount++;
        if (!rafId) {
          rafId = requestAnimationFrame(() => {
            rafId = null;
            setResults({
              campgrounds_checked: checkedCount,
              campgrounds_with_availability: streamedResults.filter(
                (r) => r.total_available_sites > 0,
              ).length,
              results: [...streamedResults],
              warnings: streamedWarnings,
            });
          });
        }
      },
      () => {
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
        setLoading(false);
        searchAbortRef.current = null;
        const withAvail = streamedResults.filter(
          (r) => r.total_available_sites > 0,
        ).length;
        setResults({
          campgrounds_checked: checkedCount,
          campgrounds_with_availability: withAvail,
          results: [...streamedResults],
          warnings: streamedWarnings,
        });
        track("search_executed", {
          search_id: searchId,
          state: params.state || "all",
          nights: params.nights || 2,
          result_count: withAvail,
          total_checked: streamedResults.length,
          mode,
          days_preset: params.days_of_week || "any",
          date_range_days: dateRangeDays(params),
          lead_time_days: leadTimeDays(params),
          radius_minutes: params.max_drive || 0,
          tag_count: params.tags ? params.tags.split(",").length : 0,
          tags: params.tags || "",
          is_nl_query: params.q ? 1 : 0,
          elapsed_ms: Math.round(performance.now() - startedAt),
        });
        if (user) {
          saveSearchHistory(params, withAvail);
        }
      },
      (err) => {
        setError(err.message);
        setLoading(false);
        searchAbortRef.current = null;
        track("search_failed", {
          search_id: searchId,
          reason: err.message.slice(0, 120),
          state: params.state || "all",
          results_received_before_failure: streamedResults.length,
          elapsed_ms: Math.round(performance.now() - startedAt),
        });
      },
      (diagEvent: DiagnosisEvent) => {
        setResults((prev) =>
          prev
            ? {
                ...prev,
                diagnosis: diagEvent.diagnosis ?? undefined,
                date_suggestions: diagEvent.date_suggestions,
                action_chips: diagEvent.action_chips,
              }
            : prev,
        );
      },
      abortController.signal,
      (parsed) => {
        if (parsed.start_date && parsed.end_date) {
          setSearchDates({ start: parsed.start_date, end: parsed.end_date });
        }
        setActiveSearchParams({
          ...params,
          start_date: parsed.start_date,
          end_date: parsed.end_date,
          state: parsed.state || undefined,
          nights: parsed.nights,
          tags: parsed.tags || undefined,
          from_location: parsed.from_location || undefined,
          max_drive: parsed.max_drive || undefined,
          name: parsed.name || undefined,
          days_of_week: parsed.days_of_week || undefined,
        });
      },
      (text) => setSearchSummary(text),
      (checked) => {
        checkedCount = checked;
        if (!rafId) {
          rafId = requestAnimationFrame(() => {
            rafId = null;
            setResults({
              campgrounds_checked: checkedCount,
              campgrounds_with_availability: streamedResults.filter(
                (r) => r.total_available_sites > 0,
              ).length,
              results: [...streamedResults],
              warnings: streamedWarnings,
            });
          });
        }
      },
      (warnings) => {
        streamedWarnings = warnings;
        setResults((prev) =>
          prev ? { ...prev, warnings } : prev,
        );
      },
    );
  }, [user]);

  // Run the search a shared link describes. Without this the URL round-trip is
  // write-only: the address bar looks right, the form shows defaults, and no
  // results appear. Fires once — restoredRef guards StrictMode's double-invoke
  // and any later re-render.
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const fromUrl = parseSearchParamsFromUrl();
    if (fromUrl) {
      handleSearch(fromUrl, (fromUrl.mode as SearchMode) || "find");
    }
  }, [handleSearch]);

  return {
    searchId: searchIdRef.current,
    results,
    searchSummary,
    setSearchSummary,
    loading,
    error,
    resultsView,
    setResultsView,
    searchDates,
    sourceFilter,
    resultSources,
    filteredResults,
    activeSearchParams,
    formCollapsed,
    setFormCollapsed,
    focusedCardIndex,
    setFocusedCardIndex,
    liveAnnouncement,
    setLiveAnnouncement,
    cardRefs,
    maxResults,
    handleSearch,
    toggleSource,
    resetSearch: useCallback(() => {
      setResults(null);
      setFormCollapsed(false);
      setSearchSummary("");
    }, []),
  };
}
