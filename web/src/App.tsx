import { useEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from "react";
import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import { getSearchHistory, getRecommendations } from "./api";
import type {
  Recommendation, SearchParams,
  SearchHistoryEntry,
} from "./api";
import { WatchPanel } from "./components/WatchPanel";
import { CalendarHeatMap } from "./components/CalendarHeatMap";
import { ResultCard, SOURCE_LABELS } from "./components/ResultCard";
import { CompareBar } from "./components/CompareBar";
import { OnboardingModal } from "./components/OnboardingModal";
const AuthModal = lazy(() => import("./components/AuthModal").then(m => ({ default: m.AuthModal })));
const ShortcutHelpModal = lazy(() => import("./components/ShortcutHelpModal").then(m => ({ default: m.ShortcutHelpModal })));
import { UserMenu } from "./components/UserMenu";
import { SmartZeroState } from "./components/SmartZeroState";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Wordmark } from "./Wordmark";
import { useAuth } from "./hooks/useAuth";
import { useSearch } from "./hooks/useSearch";
import type { SearchMode } from "./hooks/useSearch";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { SearchContext } from "./contexts/SearchContext";
const TripPlanner = lazy(() => import("./pages/TripPlanner"));
const MapView = lazy(() => import("./pages/MapView"));
const TripsPage = lazy(() => import("./pages/TripsPage"));
const TripDetail = lazy(() => import("./pages/TripDetail"));

import "./tokens.css";
import "./App.css";

function formatDate(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().split("T")[0];
}



// Map a freetext home_base to a known drive-from key
const KNOWN_BASE_KEYS = [
  "seattle", "bellevue", "portland", "spokane", "bellingham",
  "bend", "bozeman", "missoula", "jackson", "sacramento", "reno", "moscow",
];

function resolveHomeBase(homeBase: string): string {
  if (!homeBase) return "";
  const lower = homeBase.toLowerCase().replace(/[^a-z]/g, " ").trim();
  for (const key of KNOWN_BASE_KEYS) {
    if (lower.startsWith(key) || lower === key) return key;
  }
  return "";
}

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_PRESETS: Record<string, [string, string]> = {
  "": ["Any", ""],
  "4,5,6": ["Weekend", "F–Su"],
  "3,4,5,6": ["Long weekend", "Th–Su"],
  "0,1,2,3,4": ["Weekdays", ""],
};

// ─── Date Quick Presets ──────────────────────────────────────────────

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function getQuickPresets(): Array<{ label: string; start: string; end: string }> {
  const today = new Date();
  const day = today.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  const add = (base: Date, days: number) => {
    const d = new Date(base);
    d.setDate(d.getDate() + days);
    return d;
  };

  const daysToFri = ((5 - day) + 7) % 7 || 7;
  const thisFri = add(today, daysToFri);
  const thisSun = add(thisFri, 2);
  const nextFri = add(thisFri, 7);
  const nextSun = add(nextFri, 2);

  return [
    { label: "This weekend", start: fmt(thisFri), end: fmt(thisSun) },
    { label: "Next weekend", start: fmt(nextFri), end: fmt(nextSun) },
    { label: "Next 30 days", start: fmt(today), end: fmt(add(today, 30)) },
  ];
}

/** Returns month options: {month, year, label} for the next 6 months starting from next month */
function getMonthOptions(): Array<{ month: number; year: number; label: string }> {
  const today = new Date();
  const results: Array<{ month: number; year: number; label: string }> = [];
  for (let i = 1; i <= 6; i++) {
    const d = new Date(today.getFullYear(), today.getMonth() + i, 1);
    results.push({ month: d.getMonth(), year: d.getFullYear(), label: MONTH_NAMES[d.getMonth()] });
  }
  return results;
}

/** Given a set of "YYYY-MM" keys, compute the date range spanning all selected months */
function monthSetToDateRange(keys: Set<string>): { start: string; end: string } | null {
  if (keys.size === 0) return null;
  const sorted = Array.from(keys).sort();
  const [firstY, firstM] = sorted[0].split("-").map(Number);
  const [lastY, lastM] = sorted[sorted.length - 1].split("-").map(Number);
  const start = new Date(firstY, firstM, 1);
  const end = new Date(lastY, lastM + 1, 0); // last day of month
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  return { start: fmt(start), end: fmt(end) };
}

// ─── Day of Week Picker ──────────────────────────────────────────────

function DayPicker({
  selected,
  onChange,
}: {
  selected: Set<number>;
  onChange: (days: Set<number>) => void;
}) {
  const toggle = (day: number) => {
    const next = new Set(selected);
    if (next.has(day)) next.delete(day);
    else next.add(day);
    onChange(next);
  };

  return (
    <div className="day-picker" role="group" aria-label="Days of week">
      {DAY_NAMES.map((name, i) => (
        <button
          key={i}
          type="button"
          className={`day-btn ${selected.has(i) ? "active" : ""}`}
          onClick={() => toggle(i)}
          aria-pressed={selected.has(i)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

// ─── Search Form ─────────────────────────────────────────────────────

function SearchForm({
  onSearch,
  userDefaults,
  isLoggedIn,
  initialValues,
}: {
  onSearch: (params: SearchParams, mode: SearchMode) => void;
  userDefaults?: { state: string; nights: number; from: string };
  isLoggedIn: boolean;
  initialValues?: SearchParams | null;
}) {
  const [mode, setMode] = useState<SearchMode>(initialValues?.mode as SearchMode || "find");
  const [startDate, setStartDate] = useState(initialValues?.start_date || formatDate(14));
  const [endDate, setEndDate] = useState(initialValues?.end_date || formatDate(44));
  const [state, setState] = useState(initialValues?.state || userDefaults?.state || "WA");
  const [nights, setNights] = useState(initialValues?.nights || userDefaults?.nights || 2);
  const [dayPreset, setDayPreset] = useState(initialValues?.days_of_week || "");
  const [customDays, setCustomDays] = useState<Set<number>>(new Set());
  const [name, setName] = useState(initialValues?.name || "");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(
    initialValues?.tags ? new Set(initialValues.tags.split(",")) : new Set()
  );
  const [fromLocation, setFromLocation] = useState(initialValues?.from_location || userDefaults?.from || "seattle");
  const [maxDrive, setMaxDrive] = useState(initialValues?.max_drive ? String(initialValues.max_drive) : "");
  const [limit, setLimit] = useState(initialValues?.limit || 20);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [nlQuery, setNlQuery] = useState("");
  const [activeDatePreset, setActiveDatePreset] = useState<string | null>(null);
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set());
  const quickPresets = useMemo(() => getQuickPresets(), []);
  const monthOptions = useMemo(() => getMonthOptions(), []);

  // Apply user defaults when they arrive async (after auth check)
  const defaultsApplied = useRef(false);
  useEffect(() => {
    if (userDefaults && !defaultsApplied.current) {
      defaultsApplied.current = true;
      if (userDefaults.state) setState(userDefaults.state);
      if (userDefaults.nights) setNights(userDefaults.nights);
      if (userDefaults.from) setFromLocation(userDefaults.from);
    }
  }, [userDefaults]);

  // Recent searches (logged-in users only)
  const [recentSearches, setRecentSearches] = useState<SearchHistoryEntry[]>([]);
  useEffect(() => {
    if (isLoggedIn) {
      getSearchHistory().then(setRecentSearches).catch(() => {});
    } else {
      setRecentSearches([]);
    }
  }, [isLoggedIn]);

  const applyRecent = useCallback((params: SearchParams) => {
    if (params.start_date) setStartDate(params.start_date);
    if (params.end_date) setEndDate(params.end_date);
    if (params.state) setState(params.state);
    if (params.nights) setNights(params.nights);
    if (params.from_location) setFromLocation(params.from_location);
    if (params.name) setName(params.name);
    if (params.max_drive) setMaxDrive(String(params.max_drive));
    if (params.mode) setMode(params.mode as SearchMode);
  }, []);

  const getDaysOfWeek = (): string | undefined => {
    if (mode === "exact") return undefined;
    if (dayPreset === "custom") {
      return customDays.size > 0
        ? Array.from(customDays).sort().join(",")
        : undefined;
    }
    return dayPreset || undefined;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(
      {
        start_date: startDate,
        end_date: endDate,
        mode,
        state: state || undefined,
        nights: mode === "exact" ? 1 : nights,
        days_of_week: getDaysOfWeek(),
        name: name || undefined,
        tags: selectedTags.size > 0 ? Array.from(selectedTags).join(",") : undefined,
        from_location: fromLocation || undefined,
        max_drive: maxDrive ? Number(maxDrive) : undefined,
        limit,
      },
      mode
    );
  };

  return (
    <form onSubmit={handleSubmit} className="search-form">
      {/* Natural language quick search */}
      <div className="nl-search-section">
        <div className="nl-search-row">
          <input
            type="text"
            className="nl-search-input"
            placeholder="Quick search: dog-friendly lakeside spot near Portland this weekend"
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            aria-label="Quick search in plain language"
            onKeyDown={(e) => {
              if (e.key === "Enter" && nlQuery.trim()) {
                e.preventDefault();
                onSearch(
                  { start_date: "", end_date: "", q: nlQuery.trim() } as SearchParams,
                  "find",
                );
                setNlQuery("");
              }
            }}
          />
          {nlQuery.trim() && (
            <button
              type="button"
              className="nl-search-btn"
              onClick={() => {
                onSearch(
                  { start_date: "", end_date: "", q: nlQuery.trim() } as SearchParams,
                  "find",
                );
                setNlQuery("");
              }}
            >
              Go
            </button>
          )}
        </div>
      </div>
      <div className="mode-toggle">
        <button
          type="button"
          className={mode === "find" ? "active" : ""}
          onClick={() => setMode("find")}
          aria-pressed={mode === "find"}
        >
          Find a date
        </button>
        <button
          type="button"
          className={mode === "exact" ? "active" : ""}
          onClick={() => setMode("exact")}
          aria-pressed={mode === "exact"}
        >
          Exact dates
        </button>
      </div>

      {/* Trip type — primary filter, only in "Find a date" mode */}
      {mode === "find" && (
        <>
          <div
            className="trip-type"
            role="group"
            aria-label="Trip type"
          >
            {Object.entries(DAY_PRESETS).map(([val, [label, hint]]) => (
                <button
                  key={val}
                  type="button"
                  className={`trip-type-btn ${dayPreset === val ? "active" : ""}`}
                  aria-pressed={dayPreset === val}
                  onClick={() => setDayPreset(val)}
                >
                  {label}
                  {hint && <span className="trip-type-hint">{hint}</span>}
                </button>
              ))}
            <button
              type="button"
              className={`trip-type-btn ${dayPreset === "custom" ? "active" : ""}`}
              aria-pressed={dayPreset === "custom"}
              onClick={() => setDayPreset("custom")}
            >
              Custom
            </button>
          </div>
          {dayPreset === "custom" && (
            <DayPicker selected={customDays} onChange={setCustomDays} />
          )}
        </>
      )}

      {/* Date quick presets + month picker */}
      <div className="date-presets-wrap">
        <div className="date-presets" role="group" aria-label="Quick date range">
          {quickPresets.map((p) => (
            <button
              key={p.label}
              type="button"
              className={`date-preset-btn ${activeDatePreset === p.label ? "active" : ""}`}
              aria-pressed={activeDatePreset === p.label}
              onClick={() => {
                setStartDate(p.start);
                setEndDate(p.end);
                setActiveDatePreset(p.label);
                setSelectedMonths(new Set());
              }}
            >
              {p.label}
            </button>
          ))}
          <span className="date-presets-sep" aria-hidden="true" />
          {monthOptions.map((m) => {
            const key = `${m.year}-${String(m.month).padStart(2, "0")}`;
            const isActive = selectedMonths.has(key);
            return (
              <button
                key={key}
                type="button"
                className={`date-preset-btn ${isActive ? "active" : ""}`}
                aria-pressed={isActive}
                onClick={() => {
                  const next = new Set(selectedMonths);
                  if (next.has(key)) next.delete(key); else next.add(key);
                  setSelectedMonths(next);
                  setActiveDatePreset(null);
                  const range = monthSetToDateRange(next);
                  if (range) { setStartDate(range.start); setEndDate(range.end); }
                }}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Dates + nights */}
      <div className={mode === "find" ? "form-row form-row-3" : "form-row"}>
        <label>
          {mode === "find" ? "From" : "Check in"}
          <input
            type="date"
            value={startDate}
            onChange={(e) => { setStartDate(e.target.value); setActiveDatePreset(null); setSelectedMonths(new Set()); }}
            required
          />
        </label>
        <label>
          {mode === "find" ? "Through" : "Check out"}
          <input
            type="date"
            value={endDate}
            onChange={(e) => { setEndDate(e.target.value); setActiveDatePreset(null); setSelectedMonths(new Set()); }}
            required
          />
        </label>
        {mode === "find" && (
          <label>
            Nights
            <input
              type="number"
              value={nights}
              onChange={(e) => setNights(Number(e.target.value))}
              min={1}
              max={14}
            />
          </label>
        )}
      </div>

      {/* From + Max Drive */}
      <div className="form-row">
        <label>
          Drive from
          <select value={fromLocation} onChange={(e) => setFromLocation(e.target.value)}>
            <option value="seattle">Seattle</option>
            <option value="bellevue">Bellevue</option>
            <option value="portland">Portland</option>
            <option value="spokane">Spokane</option>
            <option value="bellingham">Bellingham</option>
            <option value="bend">Bend, OR</option>
            <option value="bozeman">Bozeman, MT</option>
            <option value="missoula">Missoula, MT</option>
            <option value="jackson">Jackson, WY</option>
            <option value="sacramento">Sacramento, CA</option>
            <option value="reno">Reno, NV</option>
            <option value="moscow">Moscow, ID</option>
          </select>
        </label>
        <label>
          Max drive time
          <select value={maxDrive} onChange={(e) => setMaxDrive(e.target.value)}>
            <option value="">Any length</option>
            <option value="60">Under 1 hr</option>
            <option value="120">Under 2 hrs</option>
            <option value="180">Under 3 hrs</option>
            <option value="240">Under 4 hrs</option>
            <option value="300">Under 5 hrs</option>
          </select>
        </label>
      </div>

      {/* Name filter */}
      <label className="form-row-full">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Filter by campground name..."
          aria-label="Campground name filter"
        />
      </label>

      {/* More filters — State, Source, Max Results */}
      <button
        type="button"
        className="advanced-toggle"
        onClick={() => setShowAdvanced(!showAdvanced)}
        aria-expanded={showAdvanced}
      >
        {showAdvanced ? "Fewer filters ▴" : "More filters ▾"}
        {!showAdvanced && state && (
          <span className="filter-pills">
            <span className="filter-pill">{state}</span>
          </span>
        )}
      </button>

      {showAdvanced && (
        <div className="form-row">
          <label>
            State
            <select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="">All</option>
              <option value="WA">WA</option>
              <option value="OR">OR</option>
              <option value="ID">ID</option>
              <option value="MT">MT</option>
              <option value="WY">WY</option>
              <option value="CA">CA</option>
            </select>
          </label>
          <label>
            Max Results
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              min={1}
              max={50}
            />
          </label>
        </div>
      )}

      {/* Tags */}
      <div className="tag-picker" role="group" aria-label="Filter by tags">
        {[
          "lakeside", "riverside", "beach", "old-growth",
          "pet-friendly", "rv-friendly", "tent-only",
          "trails", "swimming", "shade", "campfire",
        ].map((tag) => (
          <button
            key={tag}
            type="button"
            className={`tag-btn ${selectedTags.has(tag) ? "active" : ""}`}
            aria-pressed={selectedTags.has(tag)}
            onClick={() => {
              const next = new Set(selectedTags);
              if (next.has(tag)) next.delete(tag);
              else next.add(tag);
              setSelectedTags(next);
            }}
          >
            {tag}
          </button>
        ))}
      </div>

      {recentSearches.length > 0 && (
        <div className="recent-searches">
          <span className="recent-label">Recent</span>
          {recentSearches.slice(0, 5).map((entry, i) => {
            const p = entry.params;
            const label = [
              p.name,
              p.state,
              p.start_date?.slice(5),
            ].filter(Boolean).join(" · ") || "Search";
            return (
              <button
                key={i}
                type="button"
                className="recent-chip"
                onClick={() => applyRecent(p)}
                title={`${p.start_date} → ${p.end_date}`}
              >
                {label}
                {entry.result_count > 0 && (
                  <span className="recent-count">
                    {entry.result_count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      <button type="submit" className="search-btn">
        Search
      </button>
    </form>
  );
}

// ─── Results: Date Block View (Option B) ─────────────────────────────

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T12:00:00");
  const e = new Date(end + "T12:00:00");
  const sMonth = s.toLocaleDateString("en-US", { month: "short" });
  const eMonth = e.toLocaleDateString("en-US", { month: "short" });
  if (sMonth === eMonth) {
    return `${sMonth} ${s.getDate()}–${e.getDate()}`;
  }
  return `${sMonth} ${s.getDate()} – ${eMonth} ${e.getDate()}`;
}

const STATE_LABELS: Record<string, string> = { WA: "WA", OR: "OR", ID: "ID" };

function SearchSummaryBar({
  params,
  dates,
  onEdit,
}: {
  params: SearchParams;
  dates: { start: string; end: string };
  onEdit: () => void;
}) {
  const { user } = useAuth();
  const [watchSaved, setWatchSaved] = useState(false);
  const parts: string[] = [];
  if (params.state) parts.push(`${STATE_LABELS[params.state] || params.state} parks`);
  parts.push(formatDateRange(dates.start, dates.end));
  if (params.nights) parts.push(`${params.nights} night${params.nights !== 1 ? "s" : ""}`);
  if (params.tags) parts.push(params.tags);
  if (params.name) parts.push(`"${params.name}"`);

  const handleWatchSearch = async () => {
    const { createWatch } = await import("./api");
    const searchParams: Record<string, unknown> = {};
    if (params.state) searchParams.state = params.state;
    if (params.tags) searchParams.tags = params.tags.split(",");
    if (params.from_location) searchParams.from_location = params.from_location;
    if (params.max_drive) searchParams.max_drive = params.max_drive;
    if (params.name) searchParams.name = params.name;
    await createWatch({
      start_date: dates.start,
      end_date: dates.end,
      min_nights: params.nights || 2,
      watch_type: "template",
      search_params: searchParams,
      name: parts.join(" · "),
    });
    setWatchSaved(true);
    setTimeout(() => setWatchSaved(false), 3000);
  };

  return (
    <div className="search-summary-bar">
      <p className="search-summary-text">{parts.join(" · ")}</p>
      <div className="search-summary-actions">
        {user && (
          watchSaved
            ? <span className="watch-search-saved">Watching</span>
            : <button className="watch-search-btn" onClick={handleWatchSearch} type="button">
                Watch this search
              </button>
        )}
        <button className="search-summary-edit" onClick={onEdit} type="button">
          Edit
        </button>
      </div>
    </div>
  );
}

function FirstVisitState({ onSearch }: { onSearch: (params: SearchParams, mode: SearchMode) => void }) {
  const presets = getQuickPresets();
  const suggestions = [
    { label: "Weekend getaway in WA", params: { start_date: presets[0].start, end_date: presets[0].end, state: "WA", nights: 2 } },
    { label: "Lakeside in the next 30 days", params: { start_date: presets[2].start, end_date: presets[2].end, tags: "lakeside", nights: 2 } },
    { label: "Camping near Portland", params: { start_date: presets[1].start, end_date: presets[1].end, from_location: "portland", nights: 2 } },
  ];
  return (
    <div className="first-visit">
      <p className="first-visit-title">Find your next campsite</p>
      <p className="first-visit-subtitle">Search across WA, OR, ID, MT, WY, and Northern California</p>
      <div className="first-visit-suggestions">
        {suggestions.map((s) => (
          <button
            key={s.label}
            className="suggestion-chip"
            onClick={() => onSearch({ ...s.params, start_date: s.params.start_date, end_date: s.params.end_date } as SearchParams, "find")}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RecommendationRow({
  onSearch,
}: {
  onSearch: (params: SearchParams, mode: SearchMode) => void;
}) {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const loaded = useRef(false);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    getRecommendations().then(setRecs).catch(() => {});
  }, []);

  if (recs.length === 0) return null;

  return (
    <div className="recommendation-row">
      <p className="recommendation-title">You might like</p>
      <div className="recommendation-cards">
        {recs.map((rec) => (
          <button
            key={rec.facility_id}
            className="recommendation-card"
            onClick={() =>
              onSearch(
                {
                  start_date: formatDate(14),
                  end_date: formatDate(44),
                  name: rec.name,
                } as SearchParams,
                "find"
              )
            }
          >
            <span className="recommendation-name">{rec.name}</span>
            {rec.tags.length > 0 && (
              <span className="recommendation-tags">
                {rec.tags.slice(0, 3).join(" · ")}
              </span>
            )}
            {rec.vibe && (
              <span className="recommendation-vibe">
                {rec.vibe.length > 80 ? rec.vibe.slice(0, 80) + "…" : rec.vibe}
              </span>
            )}
            <span className="recommendation-reason">{rec.reason}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="results-skeleton" aria-busy="true" aria-label="Loading results">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton-line skeleton-title" />
          <div className="skeleton-line skeleton-summary" />
        </div>
      ))}
    </div>
  );
}


// ─── App ─────────────────────────────────────────────────────────────

export default function App() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    results, searchSummary, setSearchSummary, loading, error,
    resultsView, setResultsView,
    searchDates, sourceFilter, resultSources, filteredResults,
    activeSearchParams, formCollapsed, setFormCollapsed,
    focusedCardIndex, setFocusedCardIndex,
    liveAnnouncement, setLiveAnnouncement,
    cardRefs, maxResults, handleSearch, toggleSource,
  } = useSearch(user ?? null);

  const [watchPanelOpen, setWatchPanelOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [helpModalOpen, setHelpModalOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("campable-dark");
    if (saved !== null) return saved === "true";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  const isMap = location.pathname === "/map";
  const [mainMode, setMainMode] = useState<"search" | "plan">("search");
  const [resultsDisplay, setResultsDisplay] = useState<"list" | "map">("list");
  const [compareSet, setCompareSet] = useState<Set<string>>(new Set());

  const toggleCompare = useCallback((facilityId: string) => {
    setCompareSet(prev => {
      const next = new Set(prev);
      if (next.has(facilityId)) {
        next.delete(facilityId);
      } else if (next.size < 3) {
        next.add(facilityId);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    localStorage.setItem("campable-dark", String(darkMode));
  }, [darkMode]);

  const searchContextValue = useMemo(() => ({
    results,
    loading,
    searchDates,
    searchParams: activeSearchParams,
    sourceFilter,
    filteredResults,
  }), [results, loading, searchDates, activeSearchParams, sourceFilter, filteredResults]);

  // Close mobile menu on click outside or Escape
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(e.target as Node)) {
        setMobileMenuOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [mobileMenuOpen]);

  const availableCards = useMemo(
    () => filteredResults.filter((r) => r.total_available_sites > 0),
    [filteredResults]
  );

  const navigateCard = useCallback((delta: number) => {
    if (!availableCards.length) return;
    setFocusedCardIndex((prev) => {
      const next = Math.max(0, Math.min(availableCards.length - 1, prev + delta));
      setTimeout(() => {
        cardRefs.current[next]?.focus();
        cardRefs.current[next]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 0);
      return next;
    });
  }, [availableCards.length]);

  const shortcuts = useMemo(() => [
    { key: "j", handler: () => navigateCard(1), description: "Next result" },
    { key: "k", handler: () => navigateCard(-1), description: "Previous result" },
    { key: "w", handler: () => setWatchPanelOpen(true), description: "Open watchlist" },
    { key: "m", handler: () => { setResultsDisplay(d => { const next = d === "list" ? "map" : "list"; setLiveAnnouncement(next === "map" ? "Switched to map view" : "Switched to list view"); return next; }); }, description: "Toggle map/list" },
    { key: "?", handler: () => setHelpModalOpen(true), description: "Show shortcuts" },
  ], [navigateCard, navigate, isMap]);

  useKeyboardShortcuts(shortcuts);

  return (
    <SearchContext.Provider value={searchContextValue}>
    <div className="app">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div aria-live="polite" className="sr-only">{liveAnnouncement}</div>
      <header>
        <div className="header-row">
          <div>
            <h1><Link to="/" className="wordmark-link"><Wordmark /></Link></h1>
            <p className="header-subtitle">Find available campsites across the western US</p>
          </div>
          <div className="header-actions">
            <div className="header-secondary">
              {user && (
                <Link to="/trips" className="header-btn">
                  Trips
                </Link>
              )}
              <button
                className="header-btn watch-bell"
                onClick={() => setWatchPanelOpen(true)}
                title="Watchlist"
                aria-label="Watchlist"
              >
                🔔
              </button>
              <button
                className="header-btn theme-toggle"
                onClick={() => setDarkMode(!darkMode)}
                aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              >
                {darkMode ? "☀" : "☾"}
              </button>
              {user ? (
                <UserMenu />
              ) : (
                <button
                  className="header-btn"
                  onClick={() => setAuthModalOpen(true)}
                >
                  Sign in
                </button>
              )}
            </div>
            <div className="mobile-menu-wrapper" ref={mobileMenuRef}>
              <button
                className="header-btn mobile-menu-btn"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-expanded={mobileMenuOpen}
                aria-label="Menu"
              >
                ☰
              </button>
              {mobileMenuOpen && (
                <div className="mobile-menu">
                  <button
                    className="header-btn"
                    onClick={() => { setMainMode("plan"); navigate("/"); setMobileMenuOpen(false); }}
                  >
                    Plan a Trip
                  </button>
                  {user && (
                    <Link
                      to="/trips"
                      className="header-btn"
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      My Trips
                    </Link>
                  )}
                  <button
                    className="header-btn"
                    onClick={() => { setWatchPanelOpen(true); setMobileMenuOpen(false); }}
                  >
                    Watchlist
                  </button>
                  {user ? (
                    <UserMenu />
                  ) : (
                    <button
                      className="header-btn"
                      onClick={() => { setAuthModalOpen(true); setMobileMenuOpen(false); }}
                    >
                      Sign in
                    </button>
                  )}
                  <button
                    className="header-btn theme-toggle"
                    onClick={() => { setDarkMode(!darkMode); setMobileMenuOpen(false); }}
                    aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
                  >
                    {darkMode ? "☀ Light" : "☾ Dark"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <WatchPanel
        open={watchPanelOpen}
        onClose={() => setWatchPanelOpen(false)}
      />
      <Suspense fallback={null}>
        {authModalOpen && (
          <AuthModal
            open={authModalOpen}
            onClose={() => setAuthModalOpen(false)}
          />
        )}
        {user && !user.onboarding_complete && (
          <OnboardingModal onClose={() => {
            // Refresh user data so onboarding_complete reflects
            // (updateProfile already sets it in context)
          }} />
        )}
        {helpModalOpen && (
          <ShortcutHelpModal
            open={helpModalOpen}
            onClose={() => setHelpModalOpen(false)}
          />
        )}
      </Suspense>

      <ErrorBoundary>
      <Suspense fallback={<div className="loading-page">Loading...</div>}>
      <Routes>
        <Route path="/plan" element={<TripPlanner />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/trips/:tripId" element={<TripDetail />} />
        <Route path="/" element={
          <main id="main-content">
          <div className="mode-tabs" role="tablist" aria-label="Discovery mode">
            <button
              role="tab"
              className={`mode-tab${mainMode === "search" ? " active" : ""}`}
              aria-selected={mainMode === "search"}
              onClick={() => setMainMode("search")}
            >
              Find a Site
            </button>
            <button
              role="tab"
              className={`mode-tab${mainMode === "plan" ? " active" : ""}`}
              aria-selected={mainMode === "plan"}
              onClick={() => setMainMode("plan")}
            >
              Plan a Trip
            </button>
          </div>

          {mainMode === "plan" ? (
            <Suspense fallback={<div className="loading-page">Loading planner...</div>}>
              <TripPlanner />
            </Suspense>
          ) : (
          <>
          {formCollapsed && activeSearchParams && searchDates ? (
            <SearchSummaryBar
              params={activeSearchParams}
              dates={searchDates}
              onEdit={() => setFormCollapsed(false)}
            />
          ) : (
            <SearchForm
              onSearch={handleSearch}
              isLoggedIn={!!user}
              userDefaults={user ? {
                state: user.default_state,
                nights: user.default_nights,
                from: resolveHomeBase(user.home_base) || user.default_from,
              } : undefined}
              initialValues={activeSearchParams}
            />
          )}

      {user?.recommendations_enabled && <RecommendationRow onSearch={handleSearch} />}

      {!results && !loading && !error && <FirstVisitState onSearch={handleSearch} />}

      {error && <div className="error-banner" role="alert">{error}</div>}

      {loading && (!results || results.results.length === 0) && <ResultsSkeleton />}

      {results && (() => {
        const withAvailability = filteredResults.filter((r) => r.total_available_sites > 0).length;
        return (
        <div className="results">
          <div className="results-header">
            <p className="results-summary">
              Checked {Math.min(results.campgrounds_checked, maxResults)} campgrounds —{" "}
              {withAvailability} with availability
            </p>
            <div className="results-toolbar-right">
              <div className="view-toggle">
                <button
                  className={resultsView === "dates" ? "active" : ""}
                  onClick={() => setResultsView("dates")}
                  aria-pressed={resultsView === "dates"}
                >
                  By date
                </button>
                <button
                  className={resultsView === "sites" ? "active" : ""}
                  onClick={() => setResultsView("sites")}
                  aria-pressed={resultsView === "sites"}
                >
                  By site
                </button>
              </div>
              <div className="view-toggle map-toggle">
                <button
                  className={resultsDisplay === "list" ? "active" : ""}
                  aria-pressed={resultsDisplay === "list"}
                  onClick={() => setResultsDisplay("list")}
                >
                  ≡ List
                </button>
                <button
                  className={resultsDisplay === "map" ? "active" : ""}
                  aria-pressed={resultsDisplay === "map"}
                  onClick={() => setResultsDisplay("map")}
                >
                  ⊞ Map
                </button>
              </div>
            </div>
          </div>
          {resultSources.size > 1 && (
          <div className="source-toggle" role="group" aria-label="Filter by source">
            {[...resultSources].map((src) => {
              const count = results.results.filter((r) => r.booking_system === src && r.total_available_sites > 0).length;
              return (
                <button
                  key={src}
                  type="button"
                  className={`source-toggle-btn source-${src} ${sourceFilter.has(src) ? "active" : ""}`}
                  onClick={() => toggleSource(src)}
                  aria-pressed={sourceFilter.has(src)}
                >
                  {SOURCE_LABELS[src] || src}{count > 0 && ` (${count})`}
                </button>
              );
            })}
          </div>
          )}
          {resultsDisplay === "map" ? (
            <div className="inline-map">
              <Suspense fallback={<div className="loading-page">Loading map...</div>}>
                <MapView />
              </Suspense>
            </div>
          ) : (
          <>
          {searchDates && withAvailability > 0 && (
            <CalendarHeatMap
              results={{ ...results, results: filteredResults, campgrounds_with_availability: withAvailability }}
              startDate={searchDates.start}
              endDate={searchDates.end}
            />
          )}
          {results.warnings?.length > 0 && (
            <div className="warning-banner">
              {results.warnings.map((w, i) => (
                <p key={i}>{w.message}</p>
              ))}
            </div>
          )}
          {filteredResults.some((r) => r.booking_system === "wa_state") && (
            <p className="wa-data-note">
              <span className="source-badge source-wa_state">WA Parks</span>{" "}
              site data is limited — names, types, and capacity aren't available
              from their booking system. Check GoingToCamp for full details.
            </p>
          )}
          {searchSummary && (
            <div className="search-summary-banner" role="status">
              <div className="summary-content" dangerouslySetInnerHTML={{
                __html: (() => {
                  const lines = searchSummary.trim().split("\n").filter(l => l.trim());
                  const hasBullets = lines.some(l => l.trim().startsWith("- "));
                  if (hasBullets) {
                    const items = lines
                      .filter(l => l.trim().startsWith("- "))
                      .map(l => l.trim().replace(/^- /, "").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"))
                      .map(l => `<li>${l}</li>`)
                      .join("");
                    return `<ul>${items}</ul>`;
                  }
                  return searchSummary.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
                })()
              }} />
              <button
                type="button"
                className="summary-dismiss"
                onClick={() => setSearchSummary(null)}
                aria-label="Dismiss summary"
              >
                ×
              </button>
            </div>
          )}
          {filteredResults
            .filter((r) => r.total_available_sites > 0)
            .map((r, i) => (
              <ResultCard
                key={r.facility_id}
                result={r}
                view={resultsView}
                searchDates={searchDates || undefined}
                focused={i === focusedCardIndex}
                headerRef={(el) => { cardRefs.current[i] = el; }}
                compareSelected={compareSet.has(r.facility_id)}
                onToggleCompare={toggleCompare}
                compareDisabled={compareSet.size >= 3}
              />
            ))}
          <CompareBar
            selectedIds={compareSet}
            onClear={() => setCompareSet(new Set())}
            searchDates={searchDates || undefined}
          />
          {withAvailability === 0 && (
            <SmartZeroState
              diagnosis={
                results.campgrounds_with_availability > 0
                  ? {
                      registry_matches: results.campgrounds_checked,
                      distance_filtered: 0,
                      checked_for_availability: results.campgrounds_checked,
                      binding_constraint: "source_filter",
                      explanation:
                        "Results were found but hidden by the source filter. "
                        + "Try enabling all sources.",
                    }
                  : results?.diagnosis
              }
              dateSuggestions={results?.date_suggestions}
              actionChips={results?.action_chips}
              searchDates={searchDates || undefined}
              onSearch={handleSearch}
            />
          )}
          </>
          )}
        </div>
        );
      })()}
      </>
      )}
      </main>
        } />
      </Routes>
      </Suspense>
      </ErrorBoundary>
    </div>
    </SearchContext.Provider>
  );
}
