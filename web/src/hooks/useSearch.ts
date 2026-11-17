/** Search state and SSE stream orchestration (handleSearch). */

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { getPosthog, searchCampsitesStream, saveSearchHistory, track } from "../api";
import { answerSentence } from "../results/answer";
import type {
  CampgroundResult, SearchParams, SearchResponse, SearchWarning,
  DiagnosisEvent, SearchTiming, UserData,
} from "../api";

/**
 * Read a SearchParams back out of the query string (the inverse of what
 * handleSearch writes). Returns null unless a usable date range is present.
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
  assign("people", num("people"));
  assign("equipment", str("equipment"));
  assign("rig_length", num("rig_length"));
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

export interface UseSearchReturn {
  results: SearchResponse | null;
  loading: boolean;
  error: string | null;
  searchDates: { start: string; end: string } | null;
  sourceFilter: Set<string>;
  filteredResults: CampgroundResult[];
  activeSearchParams: SearchParams | null;
  searchId: string;
  liveAnnouncement: string;
  maxResults: number;
  /** When the last search finished streaming (ms epoch); null before one has. */
  completedAt: number | null;
  handleSearch: (params: SearchParams, mode: SearchMode) => Promise<void>;
  /** Re-run the current search with a higher `limit` to check more campgrounds. */
  checkRest: (limit: number) => void;
  resetSearch: () => void;
}

export function useSearch(user: UserData | null): UseSearchReturn {
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [completedAt, setCompletedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Set once per search, when the stream finishes; cleared when the next starts.
  const [liveAnnouncement, setLiveAnnouncement] = useState("");
  const [searchDates, setSearchDates] = useState<{ start: string; end: string } | null>(null);
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set());
  // Seeded from the URL so the search bar's first render already reflects a
  // shared link.
  const [activeSearchParams, setActiveSearchParams] = useState<SearchParams | null>(
    () => parseSearchParamsFromUrl(),
  );
  const lastSearchParams = useRef<SearchParams | null>(null);
  const lastSearchMode = useRef<SearchMode>("find");
  const searchAbortRef = useRef<AbortController | null>(null);
  // Correlates search_executed with the book_click / zero-state events it
  // produces. Exposed so result cards can stamp outbound clicks with it.
  const searchIdRef = useRef<string>("");
  // Cleared on unmount: a pending scroll that fires after teardown throws
  // "document is not defined" under vitest and flaked CI.
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(scrollTimerRef.current), []);

  const maxResults = lastSearchParams.current?.limit || 20;

  const resultSources = useMemo(() => {
    if (!results) return new Set<string>();
    return new Set(results.results.map((r) => r.booking_system));
  }, [results]);

  useEffect(() => {
    if (resultSources.size === 0) return;
    // resultSources is a fresh Set on every recompute: compare contents and
    // keep the previous Set, or every streamed frame re-renders the App twice.
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

  const handleSearch = useCallback(async (params: SearchParams, mode: SearchMode) => {
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
    // components inside a result card, and threading search_id to each of them
    // would be more invasive than the correlation is worth.
    getPosthog()?.register({ search_id: searchId });

    // Callbacks from a search this one replaced (an abort can lose the race
    // with its last frame) must not settle or overwrite this one.
    const current = () => searchIdRef.current === searchId;

    setLoading(true);
    setCompletedAt(null);
    setError(null);
    setLiveAnnouncement("");
    if (params.start_date && params.end_date) {
      setSearchDates({ start: params.start_date, end: params.end_date });
    }

    clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = setTimeout(() => {
      document.querySelector(".results")?.scrollIntoView?.({
        behavior: "smooth", block: "start",
      });
    }, 100);

    const url = new URL(window.location.href);
    url.search = "";
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== false) {
        url.searchParams.set(k, String(v));
      }
    }
    // pushState so Back undoes a search instead of leaving the site.
    if (url.toString() !== window.location.href) {
      window.history.pushState(null, "", url.toString());
    }

    const streamedResults: CampgroundResult[] = [];
    const streamedUnavailable: CampgroundResult[] = [];
    // Warnings arrive as their own SSE frame near the end of the stream.
    let streamedWarnings: SearchWarning[] = [];
    // Diagnosis and not-released frames arrive just before [DONE]. Every
    // update rebuilds `results` from this snapshot so onDone can't drop them.
    let streamedEnd: Partial<SearchResponse> = {};
    // For search_executed: what the user waited for, and which source held it.
    let firstResultMs: number | undefined;
    let timing: SearchTiming | undefined;
    let rafId: number | null = null;
    let checkedCount = 0;
    let plannedCount: number | undefined;
    // Known only once the stream finishes; undefined until then.
    let matchedCount: number | undefined;
    // What the results page words its headline from: the request, or the dates
    // and filters the server parsed out of a natural-language one.
    let announcedParams: SearchParams = params;
    const snapshot = (): SearchResponse => ({
      campgrounds_checked: checkedCount,
      campgrounds_matched: matchedCount,
      campgrounds_planned: plannedCount,
      campgrounds_with_availability: streamedResults.filter(
        (r) => r.total_available_sites > 0,
      ).length,
      results: [...streamedResults],
      unavailable: [...streamedUnavailable],
      warnings: streamedWarnings,
      ...streamedEnd,
    });
    const scheduleFlush = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        if (current()) setResults(snapshot());
      });
    };
    setResults({
      campgrounds_checked: 0,
      campgrounds_with_availability: 0,
      results: [],
      warnings: [],
    });

    await searchCampsitesStream(
      params,
      (result) => {
        streamedResults.push(result);
        checkedCount++;
        if (firstResultMs === undefined && result.total_available_sites > 0) {
          firstResultMs = Math.round(performance.now() - startedAt);
        }
        scheduleFlush();
      },
      () => {
        if (!current()) return;
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
        setLoading(false);
        setCompletedAt(Date.now());
        searchAbortRef.current = null;
        const final = snapshot();
        const withAvail = final.campgrounds_with_availability;
        setResults(final);
        setLiveAnnouncement(answerSentence({
          params: announcedParams,
          open: withAvail,
          checked: final.campgrounds_checked,
          notReleased: final.not_released_campgrounds ?? 0,
          loading: false,
        }));
        track("search_executed", {
          search_id: searchId,
          state: params.state || "all",
          nights: params.nights || 2,
          result_count: withAvail,
          // Campgrounds checked (from the coverage frame), including those with nothing open.
          total_checked: checkedCount,
          oregon_timeouts: timing?.sources.or_state?.timeouts ?? 0,
          oregon_pending: timing?.sources.or_state?.pending ?? 0,
          // Left out when unknown: a source the search didn't use has no time.
          ...definedOnly({
            first_result_ms: firstResultMs,
            server_ms: timing?.total_ms,
            recgov_ms: timing?.sources.recgov?.done_ms,
            wa_state_ms: timing?.sources.wa_state?.done_ms,
            or_state_ms: timing?.sources.or_state?.done_ms,
          }),
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
        if (!current()) return;
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
        streamedEnd = {
          ...streamedEnd,
          diagnosis: diagEvent.diagnosis ?? undefined,
          date_suggestions: diagEvent.date_suggestions,
          action_chips: diagEvent.action_chips,
        };
        setResults((prev) => (prev ? { ...prev, ...streamedEnd } : prev));
      },
      abortController.signal,
      (parsed) => {
        if (parsed.start_date && parsed.end_date) {
          setSearchDates({ start: parsed.start_date, end: parsed.end_date });
        }
        announcedParams = {
          ...params,
          start_date: parsed.start_date,
          end_date: parsed.end_date,
          state: parsed.state || undefined,
          nights: parsed.nights,
          from_location: parsed.from_location || undefined,
          max_drive: parsed.max_drive || undefined,
          name: parsed.name || undefined,
          days_of_week: parsed.days_of_week || undefined,
        };
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
      () => {},
      (checked, total) => {
        checkedCount = checked;
        plannedCount = total;
        scheduleFlush();
      },
      (warnings) => {
        streamedWarnings = warnings;
        setResults((prev) =>
          prev ? { ...prev, warnings } : prev,
        );
      },
      (matched, checked) => {
        matchedCount = matched;
        checkedCount = checked;
        setResults((prev) =>
          prev
            ? { ...prev, campgrounds_matched: matched, campgrounds_checked: checked }
            : prev,
        );
      },
      (notReleased) => {
        streamedEnd = { ...streamedEnd, ...notReleased };
        setResults((prev) => (prev ? { ...prev, ...notReleased } : prev));
      },
      (unavailable) => {
        streamedUnavailable.push(unavailable);
        scheduleFlush();
      },
      (t) => {
        timing = t;
      },
    );
  }, [user]);

  const checkRest = useCallback((limit: number) => {
    // activeSearchParams, not the form's params: for a natural-language search
    // it holds the dates and filters the server parsed, so the re-run does not
    // pay for (or vary with) a second NL parse.
    const base = activeSearchParams;
    if (!base) return;
    track("check_rest_clicked", {
      from_limit: base.limit || 20,
      to_limit: limit,
      matched: results?.campgrounds_matched ?? 0,
    });
    handleSearch({ ...base, limit }, lastSearchMode.current);
  }, [activeSearchParams, handleSearch, results?.campgrounds_matched]);

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
    loading,
    error,
    searchDates,
    sourceFilter,
    filteredResults,
    activeSearchParams,
    liveAnnouncement,
    maxResults,
    completedAt,
    handleSearch,
    checkRest,
    resetSearch: useCallback(() => {
      // Stop the running search too, or it keeps "Checking…" and refills
      // the results it was asked to clear.
      searchAbortRef.current?.abort();
      searchAbortRef.current = null;
      searchIdRef.current = "";
      setLoading(false);
      setResults(null);
      setLiveAnnouncement("");
    }, []),
  };
}

function definedOnly(props: Record<string, number | undefined>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(props)) if (v !== undefined) out[k] = v;
  return out;
}
