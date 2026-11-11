import { Capacitor } from "@capacitor/core";
import { supabase } from "./lib/supabase";

// Native (Capacitor) builds load from capacitor://localhost, so relative
// URLs would resolve against the local bundle. Point them at production.
// Web is unchanged: localhost in dev, same-origin relative in prod.
const API_BASE = Capacitor.isNativePlatform()
  ? "https://campable.co"
  : import.meta.env.DEV
    ? "http://localhost:8000"
    : "";

// ---------------------------------------------------------------------------
// Event tracking
// ---------------------------------------------------------------------------

// PostHog is initialized by the snippet in index.html, which assigns the
// configured instance to window.posthog. Importing the npm package gives you a
// *different*, never-initialized instance: posthog-js guards every public
// method on an internal `__loaded` flag set only inside init(), so calls on the
// module singleton silently no-op. Every access must go through getPosthog().
export interface PostHogInstance {
  capture(event: string, props?: Record<string, unknown>): void;
  identify(distinctId: string, props?: Record<string, unknown>): void;
  reset(): void;
  register(props: Record<string, unknown>): void;
  setPersonProperties(
    set?: Record<string, unknown>,
    setOnce?: Record<string, unknown>,
  ): void;
  captureException(error: unknown, props?: Record<string, unknown>): void;
  get_distinct_id(): string;
  opt_out_capturing?(): void;
  opt_in_capturing?(): void;
  has_opted_out_capturing?(): boolean;
  /** Undefined until flags load (always, on the snippet's stub). */
  isFeatureEnabled?(key: string): boolean | undefined;
  /** Runs when flags load or reload; returns an unsubscribe on the real SDK. */
  onFeatureFlags?(callback: () => void): (() => void) | void;
}

export function getPosthog(): PostHogInstance | undefined {
  return (window as unknown as { posthog?: PostHogInstance }).posthog;
}

export function track(event: string, data: Record<string, string | number>) {
  getPosthog()?.capture(event, data);
}

/**
 * Register super properties that ride on every subsequent event.
 *
 * `platform` matters because PostHog's auto-detected $os/$browser report the
 * Capacitor iOS WebView as plain "iOS / Mobile Safari" — indistinguishable
 * from someone browsing campable.co in Safari. Without it, native app
 * behaviour is silently pooled with mobile web.
 */
export function initAnalytics() {
  const ph = getPosthog();
  if (!ph) return;
  const platform = Capacitor.isNativePlatform() ? "ios_native" : "web";
  ph.register({ platform, app_version: __APP_VERSION__ });
  ph.setPersonProperties(undefined, { first_platform: platform });
}

// ---------------------------------------------------------------------------
// Authenticated fetch — attaches Supabase Bearer token + session cookie
// ---------------------------------------------------------------------------

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const authHeaders: Record<string, string> = {};
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      authHeaders["Authorization"] = `Bearer ${session.access_token}`;
    }
  } catch {
    // Supabase unreachable — proceed without auth
  }
  return fetch(url, {
    ...init,
    credentials: "include", // Keeps campnw_session cookie for anonymous watch migration
    headers: { ...authHeaders, ...(init?.headers as Record<string, string> || {}) },
  });
}

// ---------------------------------------------------------------------------
// Typed fetch helper — eliminates untyped resp.json() calls
// ---------------------------------------------------------------------------

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await authFetch(url, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string }).detail || `Request failed: ${resp.status}`,
    );
  }
  return resp.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// SSE type guards — runtime checks instead of unsafe `as T` casts
// ---------------------------------------------------------------------------

function isSSEDiagnosis(data: unknown): data is DiagnosisEvent {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "diagnosis";
}

function isSSEParsedParams(data: unknown): data is { type: "parsed_params"; params: ParsedParams } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "parsed_params";
}

function isSSESummary(data: unknown): data is { type: "summary"; text: string } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "summary";
}

function isSSEProgress(data: unknown): data is { type: "progress"; checked: number; total: number } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "progress";
}

function isSSEWarnings(data: unknown): data is { type: "warnings"; warnings: SearchWarning[] } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "warnings";
}

function isSSECoverage(
  data: unknown,
): data is { type: "coverage"; campgrounds_matched: number; campgrounds_checked: number } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "coverage";
}

function isSSENotReleased(data: unknown): data is { type: "not_released" } & NotReleasedSummary {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "not_released";
}

function isSSEUnavailable(data: unknown): data is { type: "unavailable"; result: CampgroundResult } {
  return typeof data === "object" && data !== null
    && (data as Record<string, unknown>).type === "unavailable";
}

function isCampgroundResult(data: unknown): data is CampgroundResult {
  return typeof data === "object" && data !== null
    && typeof (data as Record<string, unknown>).facility_id === "string"
    && !("type" in (data as Record<string, unknown>));
}

export interface Window {
  campsite_id: string;
  site_name: string;
  loop: string;
  campsite_type: string;
  start_date: string;
  end_date: string;
  nights: number;
  max_people: number;
  /** False when max_people is a provider placeholder: show no capacity. */
  max_people_known?: boolean;
  is_fcfs: boolean;
  booking_url: string | null;
  // Site fit; null = the booking system doesn't say (never "doesn't fit").
  // fits_rv true with max_rv_ft null means RVs fit but no length is listed.
  fits_tent: boolean | null;
  fits_van: boolean | null;
  fits_rv: boolean | null;
  max_rv_ft: number | null;
  hookups: boolean | null;
  walk_in: boolean | null;
}

export interface CampgroundResult {
  facility_id: string;
  name: string;
  state: string;
  region?: string;
  booking_system: string;
  latitude: number;
  longitude: number;
  total_available_sites: number;
  fcfs_sites: number;
  tags: string[];
  vibe?: string;
  elevator_pitch?: string;
  description_rewrite?: string;
  best_for?: string;
  estimated_drive_minutes: number | null;
  /** Only reachable by boat; drive time is omitted and the card says so. */
  boat_in?: boolean;
  availability_url: string | null;
  windows: Window[];
  error: string | null;
  weather_temp_high_f?: number;
  weather_temp_low_f?: number;
  weather_precip_pct?: number;
  image_urls?: string[];
  image_attribution?: string;
  /** Requested nights not yet released for booking, and when the first opens. */
  not_released_nights?: number;
  releases_on?: string | null;
  /** Which nights: consecutive runs; night N of a run opens on releases_on + N days. */
  not_released_ranges?: NotReleasedRange[];
  /** Nights nothing can be reserved online: closed, first-come only, or no data. Not "full". */
  closed_ranges?: { start: string; end: string }[];
}

export interface NotReleasedRange {
  /** First and last night, YYYY-MM-DD. */
  start: string;
  end: string;
  /** When `start` opens for booking; null when the booking system has no rule. */
  releases_on: string | null;
}

/**
 * Checked campgrounds with requested nights not yet released for booking —
 * including those with no availability, which aren't in `results` — and the
 * span of release dates (YYYY-MM-DD) from their first to last such night.
 */
export interface NotReleasedSummary {
  not_released_campgrounds: number;
  releases_on_earliest: string | null;
  releases_on_latest: string | null;
}

export interface SearchWarning {
  kind: string;
  count: number;
  source: string;
  message: string;
}

export interface Diagnosis {
  registry_matches: number;
  distance_filtered: number;
  checked_for_availability: number;
  binding_constraint: string;
  explanation: string;
}

export interface DateSuggestion {
  start_date: string;
  end_date: string;
  campgrounds_with_availability: number;
  reason: string;
}

export interface ActionChip {
  action: string;
  label: string;
  params: Record<string, unknown>;
}

export interface SearchResponse extends Partial<NotReleasedSummary> {
  campgrounds_checked: number;
  /**
   * Campgrounds that passed every registry, tag and distance filter — the
   * pool the `limit` cap selects from. `matched > checked` means the search
   * was capped. Optional because a streaming search only learns it at the end.
   */
  campgrounds_matched?: number;
  campgrounds_with_availability: number;
  results: CampgroundResult[];
  /**
   * Checked campgrounds with nothing to book (full, or not released yet),
   * from the stream's `unavailable` frames. Results v2 lists them (D4).
   */
  unavailable?: CampgroundResult[];
  warnings: SearchWarning[];
  diagnosis?: Diagnosis;
  date_suggestions?: DateSuggestion[];
  action_chips?: ActionChip[];
}

export interface SearchParams {
  start_date: string;
  end_date: string;
  q?: string;
  state?: string;
  nights?: number;
  days_of_week?: string;
  tags?: string;
  name?: string;
  source?: string;
  from_location?: string;
  max_drive?: number;
  mode?: string;
  no_groups?: boolean;
  include_fcfs?: boolean;
  limit?: number;
  /**
   * Who's going (v1.48 D5). The API drops windows at sites known not to fit;
   * sites with no type or capacity data always stay.
   */
  people?: number;
  equipment?: string;
  /** Feet, trailers only. */
  rig_length?: number;
}

const EQUIPMENT = new Set(["tent", "van", "trailer"]);

/**
 * Add the `who` filter to a search query. Values the API would reject (a
 * hand-edited URL) are left out rather than failing the search.
 */
function setWho(query: URLSearchParams, params: SearchParams): void {
  const inRange = (n: number | undefined, max: number) =>
    n !== undefined && Number.isInteger(n) && n >= 1 && n <= max;
  if (inRange(params.people, 50)) query.set("people", String(params.people));
  if (!params.equipment || !EQUIPMENT.has(params.equipment)) return;
  query.set("equipment", params.equipment);
  if (params.equipment === "trailer" && inRange(params.rig_length, 100)) {
    query.set("rig_length", String(params.rig_length));
  }
}

export async function searchCampsites(
  params: SearchParams
): Promise<SearchResponse> {
  const query = new URLSearchParams();
  query.set("start_date", params.start_date);
  query.set("end_date", params.end_date);
  if (params.state) query.set("state", params.state);
  if (params.nights) query.set("nights", String(params.nights));
  if (params.days_of_week) query.set("days_of_week", params.days_of_week);
  if (params.tags) query.set("tags", params.tags);
  if (params.name) query.set("name", params.name);
  if (params.source) query.set("source", params.source);
  if (params.from_location) query.set("from", params.from_location);
  if (params.max_drive) query.set("max_drive", String(params.max_drive));
  if (params.mode) query.set("mode", params.mode);
  if (params.no_groups) query.set("no_groups", "true");
  if (params.include_fcfs) query.set("include_fcfs", "true");
  if (params.limit) query.set("limit", String(params.limit));
  setWho(query, params);

  return fetchJson<SearchResponse>(`${API_BASE}/api/search?${query}`);
}

/** A registry campground, as `/api/campgrounds` lists it (trimmed to what the UI reads). */
export interface CampgroundMatch {
  facility_id: string;
  name: string;
  booking_system: string;
  state: string;
  region: string;
  drive_minutes_from_base: number | null;
}

/** Campgrounds whose name contains `name`, for the search bar's typeahead. */
export async function findCampgrounds(name: string, signal?: AbortSignal): Promise<CampgroundMatch[]> {
  const query = new URLSearchParams({ name, limit: "8" });
  return fetchJson<CampgroundMatch[]>(`${API_BASE}/api/campgrounds?${query}`, { signal });
}

// ---------------------------------------------------------------------------
// Streaming search (SSE)
// ---------------------------------------------------------------------------

export interface DiagnosisEvent {
  type: "diagnosis";
  diagnosis: Diagnosis | null;
  date_suggestions: DateSuggestion[];
  action_chips: ActionChip[];
}

export interface ParsedParams {
  start_date: string;
  end_date: string;
  state?: string | null;
  nights?: number;
  tags?: string | null;
  from_location?: string | null;
  max_drive?: number | null;
  name?: string | null;
  days_of_week?: string | null;
}

/**
 * How long the stream may go without a byte before the search is abandoned.
 * Every checked campground sends a frame, so this only trips when the server
 * has stalled (prod saw ~85 s gaps in a slow Oregon search that did finish).
 */
export const STREAM_IDLE_MS = 120_000;
const STREAM_STALLED = "The search stopped responding, so some campgrounds weren’t checked.";
const STREAM_CUT_OFF = "The search was cut off, so some campgrounds weren’t checked.";

/**
 * Stream a search. Always ends in exactly one of onDone (the server sent
 * [DONE]) or onError (it failed, went quiet for STREAM_IDLE_MS, or closed
 * early), except when `signal` aborts it: the caller started that.
 */
export async function searchCampsitesStream(
  params: SearchParams,
  onResult: (result: CampgroundResult) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onDiagnosis?: (event: DiagnosisEvent) => void,
  signal?: AbortSignal,
  onParsed?: (params: ParsedParams) => void,
  onSummary?: (text: string) => void,
  onProgress?: (checked: number, total: number) => void,
  onWarnings?: (warnings: SearchWarning[]) => void,
  onCoverage?: (matched: number, checked: number) => void,
  onNotReleased?: (summary: NotReleasedSummary) => void,
  onUnavailable?: (result: CampgroundResult) => void,
): Promise<void> {
  const query = new URLSearchParams();
  if (params.q) {
    query.set("q", params.q);
  }
  if (params.start_date) query.set("start_date", params.start_date);
  if (params.end_date) query.set("end_date", params.end_date);
  if (params.state) query.set("state", params.state);
  if (params.nights) query.set("nights", String(params.nights));
  if (params.days_of_week) query.set("days_of_week", params.days_of_week);
  if (params.tags) query.set("tags", params.tags);
  if (params.name) query.set("name", params.name);
  if (params.source) query.set("source", params.source);
  if (params.from_location) query.set("from", params.from_location);
  if (params.max_drive) query.set("max_drive", String(params.max_drive));
  if (params.mode) query.set("mode", params.mode);
  if (params.no_groups) query.set("no_groups", "true");
  if (params.include_fcfs) query.set("include_fcfs", "true");
  if (params.limit) query.set("limit", String(params.limit));
  setWho(query, params);

  try {
    const resp = await authFetch(`${API_BASE}/api/search/stream?${query}`, { signal });
    if (!resp.ok) throw new Error(`Search failed: ${resp.status}`);

    const reader = resp.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";
    // Cancelling the reader ends a pending read() as done, so a stalled
    // server can't hold the search in "Checking…" forever.
    let stalled = false;
    let idle: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      clearTimeout(idle);
      idle = setTimeout(() => {
        stalled = true;
        reader.cancel().catch(() => {});
      }, STREAM_IDLE_MS);
    };

    try {
      arm();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        arm();

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") {
              clearTimeout(idle);
              onDone();
              return;
            }
            try {
              const parsed: unknown = JSON.parse(data);
              if (isSSEParsedParams(parsed) && onParsed) {
                onParsed(parsed.params);
              } else if (isSSEProgress(parsed) && onProgress) {
                onProgress(parsed.checked, parsed.total);
              } else if (isSSESummary(parsed) && onSummary) {
                onSummary(parsed.text);
              } else if (isSSEWarnings(parsed) && onWarnings) {
                onWarnings(parsed.warnings);
              } else if (isSSECoverage(parsed) && onCoverage) {
                onCoverage(parsed.campgrounds_matched, parsed.campgrounds_checked);
              } else if (isSSENotReleased(parsed) && onNotReleased) {
                onNotReleased({
                  not_released_campgrounds: parsed.not_released_campgrounds,
                  releases_on_earliest: parsed.releases_on_earliest,
                  releases_on_latest: parsed.releases_on_latest,
                });
              } else if (isSSEUnavailable(parsed)) {
                onUnavailable?.(parsed.result);
              } else if (isSSEDiagnosis(parsed) && onDiagnosis) {
                onDiagnosis(parsed);
              } else if (isCampgroundResult(parsed)) {
                onResult(parsed);
              }
            } catch {
              // skip malformed lines
            }
          }
        }
      }
    } finally {
      clearTimeout(idle);
    }
    if (signal?.aborted) return;
    // The server always ends with [DONE]; without it the search is partial.
    throw new Error(stalled ? STREAM_STALLED : STREAM_CUT_OFF);
  } catch (e) {
    if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
    onError(e instanceof Error ? e : new Error("Stream failed"));
  }
}

// ---------------------------------------------------------------------------
// Watches
// ---------------------------------------------------------------------------

export interface WatchData {
  id: number;
  facility_id: string;
  name: string;
  start_date: string;
  end_date: string;
  min_nights: number;
  days_of_week: number[] | null;
  notify_topic: string;
  notification_channel: string;
  enabled: boolean;
  created_at: string;
  watch_type?: string;
  search_params?: Record<string, unknown> | null;
  /** Last night has passed (Pacific); the poller no longer checks it. */
  expired?: boolean;
}

// ---------------------------------------------------------------------------
// Trips
// ---------------------------------------------------------------------------

export interface TripCampground {
  id: number;
  facility_id: string;
  source: string;
  name: string;
  sort_order: number;
  notes: string;
  added_at: string;
}

export interface TripData {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  notes: string;
  created_at: string;
  updated_at: string;
  campground_count?: number;
  campgrounds?: TripCampground[];
}

// ---------------------------------------------------------------------------
// Comparison
// ---------------------------------------------------------------------------

export interface CompareCampground {
  facility_id: string;
  name: string;
  state: string;
  booking_system: string;
  tags: string[];
  vibe: string;
  elevator_pitch: string;
  drive_minutes: number | null;
  total_sites: number | null;
}

export interface CompareResponse {
  campgrounds: CompareCampground[];
  narrative: string | null;
}

export async function compareCampgrounds(
  facilityIds: string[],
  startDate?: string,
  endDate?: string,
): Promise<CompareResponse> {
  const resp = await authFetch(`${API_BASE}/api/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      facility_ids: facilityIds,
      start_date: startDate || "",
      end_date: endDate || "",
    }),
  });
  return resp.json();
}

// ---------------------------------------------------------------------------
// Sharing
// ---------------------------------------------------------------------------

export async function createShareLink(
  params: { watch_id?: number; trip_id?: number },
): Promise<{ uuid: string; expires_at: string }> {
  const resp = await authFetch(`${API_BASE}/api/shares`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return resp.json();
}

export interface SharedWatch {
  name: string;
  facility_id: string;
  start_date: string;
  end_date: string;
  min_nights: number;
}

export interface SharedTrip {
  name: string;
  start_date: string;
  end_date: string;
  campgrounds: { facility_id: string; source: string; name: string }[];
}

export interface SharedLinkPayload {
  uuid: string;
  type: "watch" | "trip" | null;
  watch?: SharedWatch;
  trip?: SharedTrip;
}

/** Distinguishes a dead link (revoked/expired/missing) from a transport error. */
export class ShareUnavailableError extends Error {
  // Plain field, not a parameter property — tsconfig sets erasableSyntaxOnly.
  readonly kind: "not_found" | "gone" | "rate_limited";

  constructor(kind: "not_found" | "gone" | "rate_limited") {
    super(kind);
    this.kind = kind;
  }
}

/**
 * Fetch a shared watch or trip. Public — no auth, so plain fetch rather than
 * authFetch: a recipient is by definition not signed in yet.
 */
export async function getSharedLink(uuid: string): Promise<SharedLinkPayload> {
  const resp = await fetch(`${API_BASE}/api/shared/${encodeURIComponent(uuid)}`);
  if (resp.status === 404) throw new ShareUnavailableError("not_found");
  if (resp.status === 410) throw new ShareUnavailableError("gone");
  if (resp.status === 429) throw new ShareUnavailableError("rate_limited");
  if (!resp.ok) throw new Error(`Share lookup failed (${resp.status})`);
  return resp.json();
}

export async function revokeShareLink(uuid: string): Promise<void> {
  await authFetch(`${API_BASE}/api/shares/${uuid}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Watches
// ---------------------------------------------------------------------------

export interface CreateWatchParams {
  facility_id?: string;
  name?: string;
  start_date: string;
  end_date: string;
  min_nights?: number;
  days_of_week?: number[];
  notification_channel?: string;
  watch_type?: "single" | "template";
  search_params?: Record<string, unknown>;
}


// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface UserData {
  id: number;
  email: string;
  display_name: string;
  home_base: string;
  default_state: string;
  default_nights: number;
  default_from: string;
  recommendations_enabled: boolean;
  preferred_tags: string[];
  onboarding_complete: boolean;
}

export interface Recommendation {
  facility_id: string;
  name: string;
  booking_system: string;
  state: string;
  tags: string[];
  vibe: string;
  reason: string;
}

export interface SearchHistoryEntry {
  params: SearchParams;
  result_count: number;
  searched_at: string;
}

export async function getMe(): Promise<UserData | null> {
  const resp = await authFetch(`${API_BASE}/api/auth/me`);
  if (resp.status === 401) return null;
  if (!resp.ok) return null;
  const data = await resp.json();
  return data.user;
}

export async function updateProfile(
  updates: Partial<Omit<UserData, "id" | "email">>
): Promise<UserData> {
  const resp = await authFetch(`${API_BASE}/api/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
  const data = await resp.json();
  return data.user;
}

export async function deleteAccount(): Promise<void> {
  await authFetch(`${API_BASE}/api/auth/me`, { method: "DELETE" });
}

export async function exportData(): Promise<object> {
  return fetchJson<object>(`${API_BASE}/api/auth/export`);
}

export async function getSearchHistory(): Promise<SearchHistoryEntry[]> {
  const resp = await authFetch(`${API_BASE}/api/search-history`);
  if (resp.status === 401) return [];
  if (!resp.ok) return [];
  return resp.json();
}

export async function saveSearchHistory(
  params: SearchParams,
  resultCount: number
): Promise<void> {
  // Fire-and-forget — don't await or handle errors
  authFetch(`${API_BASE}/api/search-history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params, result_count: resultCount }),
  }).catch(() => {});
}

export async function getRecommendations(): Promise<Recommendation[]> {
  try {
    const resp = await authFetch(`${API_BASE}/api/recommendations`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function getWatches(): Promise<WatchData[]> {
  return fetchJson<WatchData[]>(`${API_BASE}/api/watches`);
}

/**
 * Thrown when POST /api/watches returns HTTP 402 (free-tier cap reached).
 * UI catches this and renders <UpgradeModal>.
 */
export class WatchLimitError extends Error {
  limit: number;
  current: number;
  upgradeUrl: string;
  constructor(detail: { limit: number; current: number; upgrade_url: string }) {
    super("watch_limit_reached");
    this.name = "WatchLimitError";
    this.limit = detail.limit;
    this.current = detail.current;
    this.upgradeUrl = detail.upgrade_url;
  }
}

/**
 * Thrown when POST /api/plan/chat returns HTTP 402 — the user has used
 * their monthly trip-planner session budget. UI catches and renders
 * <UpgradeModal reason="planner_limit">.
 */
export class PlannerLimitError extends Error {
  limit: number;
  current: number;
  upgradeUrl: string;
  constructor(detail: { limit: number; current: number; upgrade_url: string }) {
    super("planner_session_limit_reached");
    this.name = "PlannerLimitError";
    this.limit = detail.limit;
    this.current = detail.current;
    this.upgradeUrl = detail.upgrade_url;
  }
}

export async function createWatch(
  params: CreateWatchParams
): Promise<WatchData> {
  const resp = await authFetch(`${API_BASE}/api/watches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (resp.status === 402) {
    const body = await resp.json().catch(() => null) as
      | { detail?: { limit: number; current: number; upgrade_url: string; error?: string } }
      | null;
    if (body?.detail?.error === "watch_limit_reached") {
      throw new WatchLimitError(body.detail);
    }
  }
  if (!resp.ok) throw new Error(`Failed to create watch: ${resp.status}`);
  return resp.json();
}

export async function deleteWatch(watchId: number): Promise<void> {
  await authFetch(`${API_BASE}/api/watches/${watchId}`, {
    method: "DELETE",
  });
}

export async function toggleWatch(
  watchId: number
): Promise<{ enabled: boolean }> {
  const resp = await authFetch(`${API_BASE}/api/watches/${watchId}/toggle`, {
    method: "PATCH",
  });
  if (!resp.ok) throw new Error(`Failed to toggle watch: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// Trip CRUD
// ---------------------------------------------------------------------------

export async function getTrips(): Promise<TripData[]> {
  return fetchJson<TripData[]>(`${API_BASE}/api/trips`);
}

export async function createTrip(
  name: string,
  opts: { start_date?: string; end_date?: string; notes?: string } = {},
): Promise<TripData> {
  const resp = await authFetch(`${API_BASE}/api/trips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...opts }),
  });
  return resp.json();
}

export async function getTrip(tripId: number): Promise<TripData> {
  return fetchJson<TripData>(`${API_BASE}/api/trips/${tripId}`);
}

export async function updateTrip(
  tripId: number,
  updates: Partial<Pick<TripData, "name" | "start_date" | "end_date" | "notes">>,
): Promise<TripData> {
  const resp = await authFetch(`${API_BASE}/api/trips/${tripId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return resp.json();
}

export async function deleteTrip(tripId: number): Promise<void> {
  await authFetch(`${API_BASE}/api/trips/${tripId}`, {
    method: "DELETE",
  });
}

export async function addCampgroundToTrip(
  tripId: number,
  facilityId: string,
  source: string = "recgov",
  name: string = "",
): Promise<TripCampground> {
  const resp = await authFetch(`${API_BASE}/api/trips/${tripId}/campgrounds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ facility_id: facilityId, source, name }),
  });
  return resp.json();
}

export async function removeCampgroundFromTrip(
  tripId: number,
  facilityId: string,
  source: string = "recgov",
): Promise<void> {
  await authFetch(`${API_BASE}/api/trips/${tripId}/campgrounds/${facilityId}?source=${source}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Web Push
// ---------------------------------------------------------------------------

export async function getVapidKey(): Promise<string> {
  const resp = await authFetch(`${API_BASE}/api/push/vapid-key`);
  if (!resp.ok) return "";
  const data = await resp.json() as { public_key?: string };
  return data.public_key || "";
}

export async function subscribePush(
  endpoint: string,
  p256dh: string,
  auth: string
): Promise<void> {
  await authFetch(`${API_BASE}/api/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint, p256dh, auth }),
  });
}

export async function unsubscribePush(endpoint: string): Promise<void> {
  await authFetch(`${API_BASE}/api/push/subscribe`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint }),
  });
}

// ---------------------------------------------------------------------------
// Trip Planner / Chat
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  result_summary?: string;
}

export interface ChatResponse {
  role: string;
  content: string;
  tool_calls: ToolCall[];
}

export async function planChat(
  messages: ChatMessage[]
): Promise<ChatResponse> {
  const resp = await authFetch(`${API_BASE}/api/plan/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (resp.status === 402) {
    const body = await resp.json().catch(() => null) as
      | { detail?: { limit: number; current: number; upgrade_url: string; error?: string } }
      | null;
    if (body?.detail?.error === "planner_session_limit_reached") {
      throw new PlannerLimitError(body.detail);
    }
  }
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || `Chat failed: ${resp.status}`);
  }
  return resp.json() as Promise<ChatResponse>;
}

export async function planChatStream(
  messages: ChatMessage[],
  onText: (chunk: string) => void,
  onToolStart: (name: string) => void,
  onToolResult: (name: string, summary: string) => void,
  onDone: (fullContent: string, toolCalls: ToolCall[]) => void,
  onError: (err: Error) => void,
): Promise<void> {
  try {
    const resp = await authFetch(`${API_BASE}/api/plan/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    if (!resp.ok) {
      if (resp.status === 402) {
        const body = await resp.json().catch(() => null) as
          | { detail?: { limit: number; current: number; upgrade_url: string; error?: string } }
          | null;
        if (body?.detail?.error === "planner_session_limit_reached") {
          throw new PlannerLimitError(body.detail);
        }
      }
      const data = await resp.json().catch(() => ({}));
      throw new Error(
        (data as { detail?: string }).detail || `Chat failed: ${resp.status}`,
      );
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") return;

        try {
          const event = JSON.parse(data);
          if (event.type === "text") {
            onText(event.content);
          } else if (event.type === "tool_start") {
            onToolStart(event.name);
          } else if (event.type === "tool_result") {
            onToolResult(event.name, event.summary);
          } else if (event.type === "done") {
            onDone(event.content, event.tool_calls || []);
            return;
          }
        } catch {
          // skip malformed events
        }
      }
    }
    // Stream ended without done event
    onDone("", []);
  } catch (e) {
    onError(e instanceof Error ? e : new Error("Stream failed"));
  }
}

// ---------------------------------------------------------------------------
// Poll status
// ---------------------------------------------------------------------------

export interface RecentNotification {
  watch_name: string;
  channel: string;
  status: string;
  changes_count: number;
  sent_at: string;
}

export interface PollStatus {
  last_poll: string | null;
  next_poll: string | null;
  active_watches: number;
  last_changes: number;
  last_errors: number;
  recent_notifications: RecentNotification[];
}

export async function getPollStatus(): Promise<PollStatus | null> {
  const resp = await authFetch(`${API_BASE}/api/poll-status`);
  if (!resp.ok) return null;
  return resp.json() as Promise<PollStatus>;
}

// ---------------------------------------------------------------------------
// Billing (v1.4)
// ---------------------------------------------------------------------------

export interface BillingStatus {
  subscription_status: "free" | "pro";
  subscription_expires_at: string;
  has_stripe_customer: boolean;
  is_pro: boolean;
  watch_limit: number | null;
  planner_session_limit: number;
  configured: boolean;
}

export async function getBillingStatus(): Promise<BillingStatus> {
  return fetchJson<BillingStatus>(`${API_BASE}/api/billing/status`);
}

/**
 * Start a Stripe Checkout Session and return the redirect URL. Caller
 * is expected to navigate to the URL via window.location to leave the
 * SPA (Stripe Checkout cannot be embedded).
 */
export async function startCheckout(): Promise<string> {
  const resp = await authFetch(`${API_BASE}/api/billing/checkout`, {
    method: "POST",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail || `Checkout failed: ${resp.status}`);
  }
  const { url } = await resp.json() as { url: string };
  return url;
}

export async function openBillingPortal(): Promise<string> {
  const resp = await authFetch(`${API_BASE}/api/billing/portal`, {
    method: "POST",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail || `Portal failed: ${resp.status}`);
  }
  const { url } = await resp.json() as { url: string };
  return url;
}
