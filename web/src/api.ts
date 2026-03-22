const API_BASE = import.meta.env.DEV ? "http://localhost:8000" : "";

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

export interface SearchResponse {
  campgrounds_checked: number;
  campgrounds_with_availability: number;
  results: CampgroundResult[];
  warnings: SearchWarning[];
}

export interface SearchParams {
  start_date: string;
  end_date: string;
  state?: string;
  nights?: number;
  days_of_week?: string;
  tags?: string;
  name?: string;
  source?: string;
  from_location?: string;
  max_drive?: number;
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
  if (params.no_groups) query.set("no_groups", "true");
  if (params.include_fcfs) query.set("include_fcfs", "true");
  if (params.limit) query.set("limit", String(params.limit));

  const resp = await fetch(`${API_BASE}/api/search?${query}`);
  if (!resp.ok) throw new Error(`Search failed: ${resp.status}`);
  return resp.json();
}
