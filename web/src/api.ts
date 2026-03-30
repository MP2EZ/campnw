const API_BASE = import.meta.env.DEV ? "http://localhost:8000" : "";

// ---------------------------------------------------------------------------
// Event tracking
// ---------------------------------------------------------------------------

export function track(event: string, data: Record<string, string | number>) {
  import("posthog-js").then(({ default: posthog }) => {
    posthog.capture(event, data);
  }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Typed fetch helper — eliminates untyped resp.json() calls
// ---------------------------------------------------------------------------

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
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
  is_fcfs: boolean;
  booking_url: string | null;
}

export interface CampgroundResult {
  facility_id: string;
  name: string;
  state: string;
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
  availability_url: string | null;
  windows: Window[];
  error: string | null;
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

export interface SearchResponse {
  campgrounds_checked: number;
  campgrounds_with_availability: number;
  results: CampgroundResult[];
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

  return fetchJson<SearchResponse>(`${API_BASE}/api/search?${query}`);
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

export async function searchCampsitesStream(
  params: SearchParams,
  onResult: (result: CampgroundResult) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onDiagnosis?: (event: DiagnosisEvent) => void,
  signal?: AbortSignal,
  onParsed?: (params: ParsedParams) => void,
  onSummary?: (text: string) => void,
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

  try {
    const resp = await fetch(`${API_BASE}/api/search/stream?${query}`, { signal });
    if (!resp.ok) throw new Error(`Search failed: ${resp.status}`);

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
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") {
            onDone();
            return;
          }
          try {
            const parsed: unknown = JSON.parse(data);
            if (isSSEParsedParams(parsed) && onParsed) {
              onParsed(parsed.params);
            } else if (isSSESummary(parsed) && onSummary) {
              onSummary(parsed.text);
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
    onDone();
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return;
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
  const resp = await fetch(`${API_BASE}/api/compare`, {
    ...fetchOpts,
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
  const resp = await fetch(`${API_BASE}/api/shares`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return resp.json();
}

export async function revokeShareLink(uuid: string): Promise<void> {
  await fetch(`${API_BASE}/api/shares/${uuid}`, {
    ...fetchOpts,
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

const fetchOpts: RequestInit = { credentials: "include" };

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

export async function signup(
  email: string,
  password: string,
  displayName?: string
): Promise<UserData> {
  const resp = await fetch(`${API_BASE}/api/auth/signup`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName || "" }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Signup failed: ${resp.status}`);
  }
  const data = await resp.json();
  return data.user;
}

export async function login(
  email: string,
  password: string
): Promise<UserData> {
  const resp = await fetch(`${API_BASE}/api/auth/login`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Login failed: ${resp.status}`);
  }
  const data = await resp.json();
  return data.user;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    ...fetchOpts,
    method: "POST",
  });
}

export async function getMe(): Promise<UserData | null> {
  const resp = await fetch(`${API_BASE}/api/auth/me`, fetchOpts);
  if (resp.status === 401) return null;
  if (!resp.ok) return null;
  const data = await resp.json();
  return data.user;
}

export async function updateProfile(
  updates: Partial<Omit<UserData, "id" | "email">>
): Promise<UserData> {
  const resp = await fetch(`${API_BASE}/api/auth/me`, {
    ...fetchOpts,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
  const data = await resp.json();
  return data.user;
}

export async function deleteAccount(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/me`, {
    ...fetchOpts,
    method: "DELETE",
  });
}

export async function exportData(): Promise<object> {
  return fetchJson<object>(`${API_BASE}/api/auth/export`, fetchOpts);
}

export async function getSearchHistory(): Promise<SearchHistoryEntry[]> {
  const resp = await fetch(`${API_BASE}/api/search-history`, fetchOpts);
  if (resp.status === 401) return [];
  if (!resp.ok) return [];
  return resp.json();
}

export async function saveSearchHistory(
  params: SearchParams,
  resultCount: number
): Promise<void> {
  // Fire-and-forget — don't await or handle errors
  fetch(`${API_BASE}/api/search-history`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params, result_count: resultCount }),
  }).catch(() => {});
}

export async function getRecommendations(): Promise<Recommendation[]> {
  try {
    const resp = await fetch(`${API_BASE}/api/recommendations`, fetchOpts);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function getWatches(): Promise<WatchData[]> {
  return fetchJson<WatchData[]>(`${API_BASE}/api/watches`, fetchOpts);
}

export async function createWatch(
  params: CreateWatchParams
): Promise<WatchData> {
  const resp = await fetch(`${API_BASE}/api/watches`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!resp.ok) throw new Error(`Failed to create watch: ${resp.status}`);
  return resp.json();
}

export async function deleteWatch(watchId: number): Promise<void> {
  await fetch(`${API_BASE}/api/watches/${watchId}`, {
    ...fetchOpts,
    method: "DELETE",
  });
}

export async function toggleWatch(
  watchId: number
): Promise<{ enabled: boolean }> {
  const resp = await fetch(`${API_BASE}/api/watches/${watchId}/toggle`, {
    ...fetchOpts,
    method: "PATCH",
  });
  if (!resp.ok) throw new Error(`Failed to toggle watch: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// Trip CRUD
// ---------------------------------------------------------------------------

export async function getTrips(): Promise<TripData[]> {
  return fetchJson<TripData[]>(`${API_BASE}/api/trips`, fetchOpts);
}

export async function createTrip(
  name: string,
  opts: { start_date?: string; end_date?: string; notes?: string } = {},
): Promise<TripData> {
  const resp = await fetch(`${API_BASE}/api/trips`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...opts }),
  });
  return resp.json();
}

export async function getTrip(tripId: number): Promise<TripData> {
  return fetchJson<TripData>(`${API_BASE}/api/trips/${tripId}`, fetchOpts);
}

export async function updateTrip(
  tripId: number,
  updates: Partial<Pick<TripData, "name" | "start_date" | "end_date" | "notes">>,
): Promise<TripData> {
  const resp = await fetch(`${API_BASE}/api/trips/${tripId}`, {
    ...fetchOpts,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return resp.json();
}

export async function deleteTrip(tripId: number): Promise<void> {
  await fetch(`${API_BASE}/api/trips/${tripId}`, {
    ...fetchOpts,
    method: "DELETE",
  });
}

export async function addCampgroundToTrip(
  tripId: number,
  facilityId: string,
  source: string = "recgov",
  name: string = "",
): Promise<TripCampground> {
  const resp = await fetch(`${API_BASE}/api/trips/${tripId}/campgrounds`, {
    ...fetchOpts,
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
  await fetch(`${API_BASE}/api/trips/${tripId}/campgrounds/${facilityId}?source=${source}`, {
    ...fetchOpts,
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Web Push
// ---------------------------------------------------------------------------

export async function getVapidKey(): Promise<string> {
  const resp = await fetch(`${API_BASE}/api/push/vapid-key`, fetchOpts);
  if (!resp.ok) return "";
  const data = await resp.json() as { public_key?: string };
  return data.public_key || "";
}

export async function subscribePush(
  endpoint: string,
  p256dh: string,
  auth: string
): Promise<void> {
  await fetch(`${API_BASE}/api/push/subscribe`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint, p256dh, auth }),
  });
}

export async function unsubscribePush(endpoint: string): Promise<void> {
  await fetch(`${API_BASE}/api/push/subscribe`, {
    ...fetchOpts,
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
  const resp = await fetch(`${API_BASE}/api/plan/chat`, {
    ...fetchOpts,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
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
    const resp = await fetch(`${API_BASE}/api/plan/chat/stream`, {
      ...fetchOpts,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    if (!resp.ok) {
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
  const resp = await fetch(`${API_BASE}/api/poll-status`, fetchOpts);
  if (!resp.ok) return null;
  return resp.json() as Promise<PollStatus>;
}
