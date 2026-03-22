import { useState } from "react";
import { searchCampsites } from "./api";
import type { SearchParams, SearchResponse } from "./api";
import "./App.css";

function formatDate(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().split("T")[0];
}

const DAY_PRESETS: Record<string, string> = {
  "": "Any day",
  "4,5,6": "Weekend (Fri-Sun)",
  "3,4,5,6": "Long weekend (Thu-Sun)",
  "0,1,2,3,4": "Weekdays",
};

function SearchForm({ onSearch, loading }: {
  onSearch: (params: SearchParams) => void;
  loading: boolean;
}) {
  const [startDate, setStartDate] = useState(formatDate(14));
  const [endDate, setEndDate] = useState(formatDate(44));
  const [state, setState] = useState("WA");
  const [nights, setNights] = useState(2);
  const [daysOfWeek, setDaysOfWeek] = useState("");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [limit, setLimit] = useState(20);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch({
      start_date: startDate,
      end_date: endDate,
      state: state || undefined,
      nights,
      days_of_week: daysOfWeek || undefined,
      name: name || undefined,
      source: source || undefined,
      limit,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="search-form">
      <div className="form-row">
        <label>
          Start Date
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
        </label>
        <label>
          End Date
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
        </label>
        <label>
          Min Nights
          <input type="number" value={nights} onChange={(e) => setNights(Number(e.target.value))} min={1} max={14} />
        </label>
      </div>
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
          Days
          <select value={daysOfWeek} onChange={(e) => setDaysOfWeek(e.target.value)}>
            {Object.entries(DAY_PRESETS).map(([val, label]) => (
              <option key={val} value={val}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">All</option>
            <option value="recgov">Rec.gov</option>
            <option value="wa_state">WA State Parks</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          Campground Name
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. rainier, lake" />
        </label>
        <label>
          Max Results
          <input type="number" value={limit} onChange={(e) => setLimit(Number(e.target.value))} min={1} max={50} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>
    </form>
  );
}

function ResultCard({ result }: { result: SearchResponse["results"][0] }) {
  const [expanded, setExpanded] = useState(false);

  if (result.error) {
    return (
      <div className="result-card error">
        <h3>{result.name}</h3>
        <p className="error-text">{result.error}</p>
      </div>
    );
  }

  // Group windows by site
  const bySite = new Map<string, typeof result.windows>();
  for (const w of result.windows) {
    if (!bySite.has(w.site_name)) bySite.set(w.site_name, []);
    bySite.get(w.site_name)!.push(w);
  }

  const sourceLabel = result.booking_system === "wa_state" ? "WA Parks" : result.state;

  return (
    <div className="result-card">
      <div className="result-header" onClick={() => setExpanded(!expanded)}>
        <div>
          <h3>{result.name} <span className="source-badge">{sourceLabel}</span></h3>
          <p className="result-summary">
            {result.total_available_sites} reservable
            {result.fcfs_sites > 0 && `, ${result.fcfs_sites} FCFS`}
            {" — "}
            {result.windows.filter(w => !w.is_fcfs).length} windows
          </p>
        </div>
        <span className="expand-icon">{expanded ? "−" : "+"}</span>
      </div>

      {result.availability_url && (
        <a href={result.availability_url} target="_blank" rel="noopener" className="book-link">
          View on {result.booking_system === "wa_state" ? "GoingToCamp" : "Recreation.gov"}
        </a>
      )}

      {expanded && (
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
                      const dayName = start.toLocaleDateString("en-US", { weekday: "short" });
                      return (
                        <a
                          key={i}
                          href={w.booking_url || result.availability_url || "#"}
                          target="_blank"
                          rel="noopener"
                          className="window-chip"
                        >
                          {dayName} {w.start_date} → {w.end_date} ({w.nights}n)
                        </a>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (params: SearchParams) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchCampsites(params);
      setResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>PNW Campsites</h1>
        <p>Find available campsites across the Pacific Northwest</p>
      </header>

      <SearchForm onSearch={handleSearch} loading={loading} />

      {error && <div className="error-banner">{error}</div>}

      {results && (
        <div className="results">
          <p className="results-summary">
            Checked {results.campgrounds_checked} campgrounds —{" "}
            {results.campgrounds_with_availability} with availability
          </p>
          {results.results
            .filter((r) => r.total_available_sites > 0 || r.error)
            .map((r) => (
              <ResultCard key={r.facility_id} result={r} />
            ))}
          {results.campgrounds_with_availability === 0 && (
            <p className="no-results">No availability found. Try broadening your search.</p>
          )}
        </div>
      )}
    </div>
  );
}
