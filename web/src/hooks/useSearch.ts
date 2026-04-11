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
import { searchCampsitesStream, saveSearchHistory, track } from "../api";
import type {
  CampgroundResult, SearchParams, SearchResponse,
  DiagnosisEvent,
} from "../api";

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
  const [activeSearchParams, setActiveSearchParams] = useState<SearchParams | null>(null);
  const [formCollapsed, setFormCollapsed] = useState(false);
  const [focusedCardIndex, setFocusedCardIndex] = useState(-1);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const lastSearchParams = useRef<SearchParams | null>(null);
  const lastSearchMode = useRef<SearchMode>("find");
  const searchAbortRef = useRef<AbortController | null>(null);

  const maxResults = lastSearchParams.current?.limit || 20;

  const resultSources = useMemo(() => {
    if (!results) return new Set<string>();
    return new Set(results.results.map((r) => r.booking_system));
  }, [results]);

  useEffect(() => {
    if (resultSources.size > 0) {
      setSourceFilter(resultSources);
    }
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
    window.history.replaceState(null, "", url.toString());

    const streamedResults: CampgroundResult[] = [];
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
              warnings: [],
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
          warnings: [],
        });
        track("search_executed", {
          state: params.state || "all",
          nights: params.nights || 2,
          result_count: withAvail,
          total_checked: streamedResults.length,
        });
        if (user) {
          saveSearchHistory(params, withAvail);
        }
      },
      (err) => {
        setError(err.message);
        setLoading(false);
        searchAbortRef.current = null;
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
              warnings: [],
            });
          });
        }
      },
    );
  }, [user]);

  return {
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
