import "@fontsource-variable/bricolage-grotesque/opsz.css";
import { useEffect, useLayoutEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from "react";
import { Helmet } from "react-helmet-async";
import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import { getPosthog, getRecommendations, track } from "./api";
import type { Recommendation, SearchParams } from "./api";
import { WatchPanel } from "./components/WatchPanel";
import { OnboardingModal } from "./components/OnboardingModal";
const AuthModal = lazy(() => import("./components/AuthModal").then(m => ({ default: m.AuthModal })));
const ShortcutHelpModal = lazy(() => import("./components/ShortcutHelpModal").then(m => ({ default: m.ShortcutHelpModal })));
import { UserMenu } from "./components/UserMenu";
import { ProBadge } from "./components/ProBadge";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Lockup } from "./components/brand/Lockup";
import { IconSun, IconMoon } from "./icons";
import { useAuth } from "./hooks/useAuth";
import { useSearch } from "./hooks/useSearch";
import type { SearchMode } from "./hooks/useSearch";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { SearchContext } from "./contexts/SearchContext";
// The bar is the page's main control, in the header on "/": loaded with the shell.
import SearchBar, { AskForm } from "./results/SearchBar";
const TripPlanner = lazy(() => import("./pages/TripPlanner"));
const MapView = lazy(() => import("./pages/MapView"));
const TripsPage = lazy(() => import("./pages/TripsPage"));
const TripDetail = lazy(() => import("./pages/TripDetail"));
const SharedView = lazy(() => import("./pages/SharedView"));
const Pricing = lazy(() => import("./pages/Pricing"));
const About = lazy(() => import("./pages/About"));
const ResultsPage = lazy(() => import("./results/ResultsPage"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Terms = lazy(() => import("./pages/Terms"));
import { Footer } from "./components/Footer";

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
  const navigate = useNavigate();
  const location = useLocation();
  const {
    results, loading, error, searchDates, sourceFilter, filteredResults,
    activeSearchParams, liveAnnouncement,
    maxResults, completedAt, handleSearch, checkRest, resetSearch, searchId,
  } = useSearch(user ?? null);

  const [watchPanelOpen, setWatchPanelOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authEntryPoint, setAuthEntryPoint] = useState("unknown");
  const [helpModalOpen, setHelpModalOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("campable-dark");
    if (saved !== null) return saved === "true";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  const [mainMode, setMainMode] = useState<"search" | "plan">("search");
  // The search bar lives in the sticky header on the search page (P4b).
  const showBar = location.pathname === "/" && mainMode === "search";
  const headerRef = useRef<HTMLElement>(null);
  // Sticky things below the header (the desktop map, a card scrolled to)
  // offset by its height, which changes with the bar and the viewport.
  useLayoutEffect(() => {
    const el = headerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const root = document.documentElement;
    const set = () => root.style.setProperty("--header-h", `${el.offsetHeight}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const handleNlSearch = useCallback((query: string) => {
    track("nl_search_submitted", { query_length: query.length });
    handleSearch(
      { start_date: "", end_date: "", q: query } as SearchParams,
      "find",
    );
  }, [handleSearch]);

  // v1.48 shipped behind the `results_v2` flag. Every page is v2 now; the
  // property stays so funnels split by ui_version read across the flip, and
  // the old per-browser ?ui= override is forgotten.
  useEffect(() => {
    getPosthog()?.register({ ui_version: "v2" });
    try {
      localStorage.removeItem("campable-ui");
    } catch {
      // Blocked storage: nothing was saved there either.
    }
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

  const shortcuts = useMemo(() => [
    { key: "w", handler: () => setWatchPanelOpen(true), description: "Open watchlist" },
    { key: "?", handler: () => setHelpModalOpen(true), description: "Show shortcuts" },
  ], []);

  useKeyboardShortcuts(shortcuts);

  return (
    <SearchContext.Provider value={searchContextValue}>
      <Helmet>
        <title>Campable — Find Available Campsites</title>
        <meta name="description" content="Search and monitor campsite availability across Washington, Oregon, Idaho, Montana, Wyoming, and Northern California." />
        <meta property="og:title" content="Campable — Find Available Campsites" />
        <meta property="og:description" content="Search and monitor campsite availability across the western US." />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/og-default.png" />
      </Helmet>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div aria-live="polite" className="sr-only">{liveAnnouncement}</div>
      {/* Outside .app so it spans the window. Each page owns its h1 (the
          answer, on the search page), so the wordmark is a plain link. */}
      <header ref={headerRef} className={`app-header${showBar ? " has-search" : ""}`}>
        <div className="header-row">
          <a href="/" className="wordmark-link" aria-label="Campable home"
            onClick={(e) => { e.preventDefault(); resetSearch(); navigate("/"); }}>
            <Lockup size={32} tone={darkMode ? "on-dark" : "on-cream"} />
          </a>
          {showBar && (
            <div className="header-search">
              <SearchBar onSearch={handleSearch}
                userDefaults={user ? { from: resolveHomeBase(user.home_base) || user.default_from, nights: user.default_nights } : undefined} />
            </div>
          )}
          <div className="header-actions">
            <nav className="header-secondary" aria-label="Main navigation">
              {user && (
                <Link to="/trips" className="header-btn">
                  Trips
                </Link>
              )}
              <button
                className="header-btn"
                onClick={() => { setWatchPanelOpen(true); track("watchlist_opened", {}); }}
              >
                Watchlist
              </button>
              <button
                className="header-btn theme-toggle"
                onClick={() => { setDarkMode(!darkMode); track("dark_mode_toggled", { to: darkMode ? "light" : "dark" }); }}
                aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              >
                {darkMode ? <IconSun className="icon" /> : <IconMoon className="icon" />}
              </button>
              {user ? (
                <>
                  <ProBadge />
                  <UserMenu />
                </>
              ) : (
                <button
                  className="header-btn"
                  onClick={() => { setAuthEntryPoint("header"); setAuthModalOpen(true); }}
                >
                  Sign in
                </button>
              )}
            </nav>
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
                      onClick={() => { setAuthEntryPoint("mobile_menu"); setAuthModalOpen(true); setMobileMenuOpen(false); }}
                    >
                      Sign in
                    </button>
                  )}
                  <button
                    className="header-btn theme-toggle"
                    onClick={() => { setDarkMode(!darkMode); setMobileMenuOpen(false); }}
                    aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
                  >
                    {darkMode ? <><IconSun className="icon" /> Light</> : <><IconMoon className="icon" /> Dark</>}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="app">
      <WatchPanel
        open={watchPanelOpen}
        onClose={() => setWatchPanelOpen(false)}
      />
      <Suspense fallback={null}>
        {authModalOpen && (
          <AuthModal
            open={authModalOpen}
            entryPoint={authEntryPoint}
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
      {/* Single main landmark for the whole app. Pages render plain
          containers: when App had its own <main> and also rendered MapView /
          TripPlanner inline, the result was a nested <main> plus a duplicate
          DOM id, while /pricing and /trips/:id had no landmark at all — so the
          skip link above resolved to two elements on some routes and none on
          others. */}
      <main id="main-content">
      <Routes>
        <Route path="/plan" element={<TripPlanner />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/trips/:tripId" element={<TripDetail />} />
        {/* ShareButton has always copied /shared/:uuid; without this route the
            recipient got the app shell and an empty content area. */}
        <Route path="/shared/:uuid" element={<SharedView />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<About />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/" element={
          <div className={showBar ? "home-frame home-frame--wide" : "home-frame"}>
          <div className="mode-tabs" role="tablist" aria-label="Discovery mode">
            <button
              role="tab"
              className={`mode-tab${mainMode === "search" ? " active" : ""}`}
              aria-selected={mainMode === "search"}
              onClick={() => { setMainMode("search"); track("mode_switched", { to_mode: "search" }); }}
            >
              Find a Site
            </button>
            <button
              role="tab"
              className={`mode-tab${mainMode === "plan" ? " active" : ""}`}
              aria-selected={mainMode === "plan"}
              onClick={() => { setMainMode("plan"); track("mode_switched", { to_mode: "plan" }); }}
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
          <AskForm onAsk={handleNlSearch} />

      {!results && !loading && (
        <div className="home-intro">
          <h1>Find available campsites across the western US</h1>
        </div>
      )}

      {user?.recommendations_enabled && <RecommendationRow onSearch={handleSearch} />}

      {error && <div className="error-banner" role="alert">{error}</div>}

      {loading && (!results || results.results.length === 0) && <ResultsSkeleton />}

      {results && (
        <Suspense fallback={null}>
          <ResultsPage maxResults={maxResults} onCheckRest={checkRest} completedAt={completedAt}
            onSearch={handleSearch} searchId={searchId} failed={!!error}
            onSignIn={() => { setAuthEntryPoint("watch_sheet"); setAuthModalOpen(true); }} />
        </Suspense>
      )}
      </>
      )}
          </div>
        } />
      </Routes>
      </main>
      </Suspense>
      </ErrorBoundary>
      <Footer />
    </div>
    </SearchContext.Provider>
  );
}