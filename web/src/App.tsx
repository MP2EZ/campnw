import { useEffect, useRef, useState } from "react";
import { searchCampsitesStream } from "./api";
import type { CampgroundResult, SearchParams, SearchResponse, Window } from "./api";
import { WatchPanel, WatchButton } from "./components/WatchPanel";
import { CalendarHeatMap } from "./components/CalendarHeatMap";

const API_BASE = import.meta.env.DEV ? "http://localhost:8000" : "";

function track(event: string, data: Record<string, string | number>) {
  try {
    navigator.sendBeacon(
      `${API_BASE}/api/track`,
      JSON.stringify({ event, ...data })
    );
  } catch {
    // ignore
  }
}

import "./App.css";

function formatDate(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().split("T")[0];
}

type SearchMode = "find" | "exact";
type ResultsView = "dates" | "sites";

const INITIAL_BLOCKS_SHOWN = 3;

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_PRESETS: Record<string, [string, string]> = {
  "": ["Any", ""],
  "4,5,6": ["Weekend", "F–Su"],
  "3,4,5,6": ["Long wknd", "Th–Su"],
  "0,1,2,3,4": ["Weekdays", ""],
};

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
  loading,
}: {
  onSearch: (params: SearchParams, mode: SearchMode) => void;
  loading: boolean;
}) {
  const [mode, setMode] = useState<SearchMode>("find");
  const [startDate, setStartDate] = useState(formatDate(14));
  const [endDate, setEndDate] = useState(formatDate(44));
  const [state, setState] = useState("WA");
  const [nights, setNights] = useState(2);
  const [dayPreset, setDayPreset] = useState("");
  const [customDays, setCustomDays] = useState<Set<number>>(new Set());
  const [name, setName] = useState("");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [fromLocation, setFromLocation] = useState("seattle");
  const [maxDrive, setMaxDrive] = useState("");
  const [limit, setLimit] = useState(20);
  const [showAdvanced, setShowAdvanced] = useState(false);

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

      {/* Dates + nights */}
      <div className={mode === "find" ? "form-row form-row-3" : "form-row"}>
        <label>
          {mode === "find" ? "From" : "Check in"}
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </label>
        <label>
          {mode === "find" ? "Through" : "Check out"}
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
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
          "trails", "swimming", "shade",
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

      <button type="submit" className="search-btn" disabled={loading}>
        {loading ? "Searching..." : "Search"}
      </button>
    </form>
  );
}

// ─── Results: Date Block View (Option B) ─────────────────────────────

interface DateBlock {
  key: string;
  start_date: string;
  end_date: string;
  nights: number;
  dayName: string;
  sites: Window[];
}

function groupByDateBlock(windows: Window[]): DateBlock[] {
  const blockMap = new Map<string, DateBlock>();
  for (const w of windows) {
    if (w.is_fcfs) continue;
    const key = `${w.start_date}→${w.end_date}`;
    if (!blockMap.has(key)) {
      const start = new Date(w.start_date + "T12:00:00");
      blockMap.set(key, {
        key,
        start_date: w.start_date,
        end_date: w.end_date,
        nights: w.nights,
        dayName: start.toLocaleDateString("en-US", { weekday: "short" }),
        sites: [],
      });
    }
    blockMap.get(key)!.sites.push(w);
  }
  return Array.from(blockMap.values()).sort((a, b) =>
    a.start_date.localeCompare(b.start_date)
  );
}

function DateBlockView({ result }: { result: SearchResponse["results"][0] }) {
  const blocks = groupByDateBlock(result.windows);
  const fcfsSites = result.windows.filter((w) => w.is_fcfs);
  const isWaState = result.booking_system === "wa_state";
  const [showAll, setShowAll] = useState(false);

  const visibleBlocks = showAll ? blocks : blocks.slice(0, INITIAL_BLOCKS_SHOWN);
  const hiddenCount = blocks.length - INITIAL_BLOCKS_SHOWN;

  return (
    <div className="site-list">
      {visibleBlocks.map((block) => (
        <div key={block.key} className="date-block">
          <div className="date-block-header">
            <span className="date-block-range">
              {block.dayName} {block.start_date} → {new Date(block.end_date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })} {block.end_date}
            </span>
            <span className="date-block-meta">
              {block.nights}n · {block.sites.length} site
              {block.sites.length !== 1 && "s"}
            </span>
          </div>
          {isWaState ? (
            <div className="date-block-sites">
              <a
                href={result.availability_url || "#"}
                target="_blank"
                rel="noopener"
                className="site-chip wa-book-link"
              >
                {block.sites.length} site
                {block.sites.length !== 1 ? "s" : ""} available
                <span className="site-chip-meta">Book on GoingToCamp</span>
              </a>
            </div>
          ) : (
            <div className="date-block-sites">
              {block.sites.map((w, i) => (
                <a
                  key={i}
                  href={w.booking_url || result.availability_url || "#"}
                  target="_blank"
                  rel="noopener"
                  className="site-chip"
                  onClick={() => track("book_click", {
                    facility_id: result.facility_id,
                    name: result.name,
                    source: result.booking_system,
                    type: "site",
                    site: w.site_name,
                  })}
                >
                  {w.site_name}
                  <span className="site-chip-meta">
                    {w.loop} · max {w.max_people}p
                  </span>
                </a>
              ))}
            </div>
          )}
        </div>
      ))}
      {!showAll && hiddenCount > 0 && (
        <button
          className="show-more-btn"
          onClick={() => setShowAll(true)}
        >
          Show {hiddenCount} more window{hiddenCount !== 1 && "s"}
        </button>
      )}
      {fcfsSites.length > 0 && (
        <div className="fcfs-section">
          <p className="fcfs-label">
            {fcfsSites.length} FCFS site{fcfsSites.length !== 1 && "s"} — not
            bookable online
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Results: Site View (Option A) ───────────────────────────────────

function SiteView({ result }: { result: SearchResponse["results"][0] }) {
  if (result.booking_system === "wa_state") {
    return <DateBlockView result={result} />;
  }

  const bySite = new Map<string, Window[]>();
  for (const w of result.windows) {
    if (!bySite.has(w.site_name)) bySite.set(w.site_name, []);
    bySite.get(w.site_name)!.push(w);
  }

  return (
    <div className="site-list">
      {Array.from(bySite.entries()).map(([siteName, windows]) => {
        const w0 = windows[0];
        return (
          <div key={siteName} className="site-group">
            <h4>
              Site {siteName}
              <span className="site-meta">
                {w0.loop} · {w0.campsite_type} · max {w0.max_people}p
              </span>
            </h4>
            {w0.is_fcfs ? (
              <p className="fcfs-label">FCFS — not bookable online</p>
            ) : (
              <div className="windows-grid">
                {windows.map((w, i) => {
                  const start = new Date(w.start_date + "T12:00:00");
                  const dayName = start.toLocaleDateString("en-US", {
                    weekday: "short",
                  });
                  return (
                    <a
                      key={i}
                      href={w.booking_url || result.availability_url || "#"}
                      target="_blank"
                      rel="noopener"
                      className="window-chip"
                    >
                      {dayName} {w.start_date} → {new Date(w.end_date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })} {w.end_date} ({w.nights}n)
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Result Card ─────────────────────────────────────────────────────

function ResultCard({
  result,
  view,
  searchDates,
}: {
  result: SearchResponse["results"][0];
  view: ResultsView;
  searchDates?: { start: string; end: string };
}) {
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      track("card_expand", {
        facility_id: result.facility_id,
        name: result.name,
        source: result.booking_system,
      });
    }
    if (next && cardRef.current) {
      setTimeout(() => {
        cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    }
  };

  if (result.error) {
    return (
      <div className="result-card error">
        <h3>{result.name}</h3>
        <p className="error-text">{result.error}</p>
      </div>
    );
  }

  const sourceLabels: Record<string, string> = {
    recgov: "Rec.gov",
    wa_state: "WA Parks",
    or_state: "OR Parks",
    id_state: "ID Parks",
  };
  const sourceLabel = sourceLabels[result.booking_system] || result.booking_system;
  const dateBlocks = groupByDateBlock(result.windows);
  const summaryText =
    view === "dates"
      ? `${result.total_available_sites} sites · ${dateBlocks.length} window${dateBlocks.length !== 1 ? "s" : ""}`
      : `${result.total_available_sites} sites · ${result.windows.filter((w) => !w.is_fcfs).length} windows`;

  return (
    <div className={`result-card card-${result.booking_system}`} ref={cardRef}>
      <button
        className="result-header"
        onClick={handleToggle}
        aria-expanded={expanded}
        type="button"
      >
        <div>
          <h3>
            {result.name}{" "}
            <span className={`source-badge source-${result.booking_system}`}>
              {sourceLabel}
            </span>
            {result.estimated_drive_minutes != null && (
              <span className="drive-badge">
                {result.estimated_drive_minutes < 60
                  ? `~${result.estimated_drive_minutes}m`
                  : `~${Math.floor(result.estimated_drive_minutes / 60)}h ${result.estimated_drive_minutes % 60}m`}
              </span>
            )}
            {(result.tags || []).slice(0, 4).map((tag) => (
              <span key={tag} className="tag-badge">{tag}</span>
            ))}
          </h3>
          <p className="result-summary">
            {summaryText}
            {result.fcfs_sites > 0 && ` + ${result.fcfs_sites} FCFS`}
          </p>
        </div>
        <span className="expand-icon" aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <>
          {result.availability_url && (
            <div className="card-toolbar">
              <a
                href={result.availability_url}
                target="_blank"
                rel="noopener"
                className="book-link"
                onClick={() => track("book_click", {
                  facility_id: result.facility_id,
                  name: result.name,
                  source: result.booking_system,
                  type: "view_page",
                })}
              >
                View on{" "}
                {result.booking_system === "wa_state"
                  ? "GoingToCamp"
                  : "Recreation.gov"}{" "}
                ↗
              </a>
              {searchDates && (
                <WatchButton
                  facilityId={result.facility_id}
                  name={result.name}
                  startDate={searchDates.start}
                  endDate={searchDates.end}
                />
              )}
            </div>
          )}
          {view === "dates" ? (
            <DateBlockView result={result} />
          ) : (
            <SiteView result={result} />
          )}
        </>
      )}
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────

export default function App() {
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultsView, setResultsView] = useState<ResultsView>("dates");
  const [searchDates, setSearchDates] = useState<{ start: string; end: string } | null>(null);
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set(["recgov", "wa_state"]));
  const [watchPanelOpen, setWatchPanelOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("campnw-dark");
    if (saved !== null) return saved === "true";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    localStorage.setItem("campnw-dark", String(darkMode));
  }, [darkMode]);

  const handleSearch = async (params: SearchParams, mode: SearchMode) => {
    setLoading(true);
    setError(null);
    setResultsView(mode === "find" ? "dates" : "sites");
    setSearchDates({ start: params.start_date, end: params.end_date });

    // Sync search params to URL for shareable links
    const url = new URL(window.location.href);
    url.search = "";
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== false) {
        url.searchParams.set(k, String(v));
      }
    }
    window.history.replaceState(null, "", url.toString());
    // Stream results as they arrive
    const streamedResults: CampgroundResult[] = [];
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
        setResults({
          campgrounds_checked: streamedResults.length,
          campgrounds_with_availability: streamedResults.filter(
            (r) => r.total_available_sites > 0
          ).length,
          results: [...streamedResults],
          warnings: [],
        });
      },
      () => {
        setLoading(false);
      },
      (err) => {
        setError(err.message);
        setLoading(false);
      },
    );
  };

  return (
    <div className="app">
      <header>
        <div className="header-row">
          <div>
            <h1>campnw</h1>
            <p>Find available campsites across the Pacific Northwest</p>
          </div>
          <div className="header-actions">
            <button
              className="header-btn"
              onClick={() => setWatchPanelOpen(true)}
              title="Watchlist"
            >
              Watchlist
            </button>
            <button
              className="header-btn theme-toggle"
              onClick={() => setDarkMode(!darkMode)}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {darkMode ? "☀" : "☾"}
            </button>
          </div>
        </div>
      </header>

      <WatchPanel
        open={watchPanelOpen}
        onClose={() => setWatchPanelOpen(false)}
      />

      <main>
      <SearchForm onSearch={handleSearch} loading={loading} />

      {error && <div className="error-banner">{error}</div>}

      {results && (() => {
        // Client-side source filtering — instant, no re-fetch
        const filteredResults = {
          ...results,
          results: results.results.filter(
            (r) => sourceFilter.has(r.booking_system)
          ),
          campgrounds_with_availability: results.results.filter(
            (r) => sourceFilter.has(r.booking_system) && r.total_available_sites > 0
          ).length,
        };
        const toggleSource = (src: string) => {
          const next = new Set(sourceFilter);
          if (next.has(src) && next.size > 1) {
            next.delete(src);
          } else if (!next.has(src)) {
            next.add(src);
          }
          setSourceFilter(next);
        };
        return (
        <div className="results">
          <div className="results-header">
            <p className="results-summary">
              Checked {results.campgrounds_checked} campgrounds —{" "}
              {filteredResults.campgrounds_with_availability} with availability
            </p>
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
          </div>
          {/* Source filter — client-side, instant toggle */}
          <div className="source-toggle" role="group" aria-label="Filter by source">
            <button
              type="button"
              className={`source-toggle-btn source-recgov ${sourceFilter.has("recgov") ? "active" : ""}`}
              onClick={() => toggleSource("recgov")}
              aria-pressed={sourceFilter.has("recgov")}
            >
              Rec.gov
            </button>
            <button
              type="button"
              className={`source-toggle-btn source-wa_state ${sourceFilter.has("wa_state") ? "active" : ""}`}
              onClick={() => toggleSource("wa_state")}
              aria-pressed={sourceFilter.has("wa_state")}
            >
              WA Parks
            </button>
          </div>
          {searchDates && filteredResults.campgrounds_with_availability > 0 && (
            <CalendarHeatMap
              results={filteredResults}
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
          {filteredResults.results.some((r) => r.booking_system === "wa_state") && (
            <p className="wa-data-note">
              <span className="source-badge source-wa_state">WA Parks</span>{" "}
              site data is limited — names, types, and capacity aren't available
              from their booking system. Check GoingToCamp for full details.
            </p>
          )}
          {filteredResults.results
            .filter((r) => r.total_available_sites > 0)
            .map((r) => (
              <ResultCard
                key={r.facility_id}
                result={r}
                view={resultsView}
                searchDates={searchDates || undefined}
              />
            ))}
          {filteredResults.campgrounds_with_availability === 0 && (
            <div className="no-results">
              <p>No availability found for these dates.</p>
              <p className="no-results-hint">
                Try different dates, a wider date range, or fewer nights.
                {searchDates && " You can also watch specific campgrounds to get notified when sites open up."}
              </p>
            </div>
          )}
        </div>
        );
      })()}
      </main>
    </div>
  );
}
