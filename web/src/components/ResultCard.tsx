import { useState, useRef, useCallback, memo } from "react";
import { track } from "../api";
import { SOURCE_LABELS } from "../lib/sources";
import { IconMinus, IconPlus } from "../icons";
import type { SearchResponse, Window } from "../api";
import { WatchButton } from "./WatchPanel";
import { SaveToTripButton } from "./SaveToTripButton";
import { HeroPhoto } from "./HeroPhoto";
import { PostcardPlaceholder } from "./PostcardPlaceholder";
import type { ResultsView } from "../hooks/useSearch";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const INITIAL_BLOCKS_SHOWN = 3;


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
    const key = `${w.start_date}\u2192${w.end_date}`;
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

function fmtDate(iso: string): string {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function meaningfulLoop(loop: string, campgroundName: string): string | null {
  const normalize = (s: string) =>
    s.toUpperCase().replace(/[^A-Z0-9]/g, " ").replace(/\s+/g, " ").trim();
  const nl = normalize(loop);
  const nc = normalize(campgroundName);
  if (!nl || nl === nc || nc.includes(nl) || nl.includes(nc)) return null;
  // Strip "AREA"/"LOOP" prefix from loop and re-check — rec.gov loops like
  // "AREA ELK CREEK CAMPGROUND" are redundant with "ELK CREEK CAMPGROUND
  // (CLEARWATER NF)" (parens already gone after normalize)
  const stripped = nl.replace(/^(AREA|LOOP)\s+/, "");
  if (stripped.length > 2 && nc.includes(stripped)) return null;
  return loop;
}

// ---------------------------------------------------------------------------
// DateBlockView
// ---------------------------------------------------------------------------

function DateBlockView({
  result, rank,
}: { result: SearchResponse["results"][0]; rank?: number }) {
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
              {block.dayName} {fmtDate(block.start_date)} &rarr; {new Date(block.end_date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })} {fmtDate(block.end_date)}
            </span>
            <span className="date-block-meta">
              {block.nights}n &middot; {block.sites.length} site
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
                onClick={() => track("book_click", {
                  facility_id: result.facility_id,
                  result_rank: rank ?? -1,
                  drive_minutes: result.estimated_drive_minutes ?? -1,
                  total_available_sites: result.total_available_sites,
                  name: result.name,
                  source: result.booking_system,
                  type: "wa_date_block",
                  sites_in_block: block.sites.length,
                  has_photo: result.image_urls?.length ? 1 : 0,
                })}
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
                  result_rank: rank ?? -1,
                  drive_minutes: result.estimated_drive_minutes ?? -1,
                  total_available_sites: result.total_available_sites,
                    name: result.name,
                    source: result.booking_system,
                    type: "site",
                    site: w.site_name,
                    has_photo: result.image_urls?.length ? 1 : 0,
                  })}
                >
                  Site {w.site_name}
                  <span className="site-chip-meta">
                    {(() => {
                      const loop = meaningfulLoop(w.loop, result.name);
                      return loop ? `${loop} \u00b7 ${w.max_people}p` : `${w.max_people}p`;
                    })()}
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
          Show {hiddenCount} more date range{hiddenCount !== 1 && "s"}
        </button>
      )}
      {fcfsSites.length > 0 && (
        <div className="fcfs-section">
          <p className="fcfs-label">
            {fcfsSites.length} First-come, first-served (FCFS) site{fcfsSites.length !== 1 && "s"} &mdash; not
            bookable online
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SiteView
// ---------------------------------------------------------------------------

function SiteView({
  result, rank,
}: { result: SearchResponse["results"][0]; rank?: number }) {
  if (result.booking_system === "wa_state") {
    return <DateBlockView result={result} rank={rank} />;
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
                {(() => {
                  const loop = meaningfulLoop(w0.loop, result.name);
                  return loop ? `${loop} \u00b7 ` : "";
                })()}{w0.campsite_type} &middot; max {w0.max_people}p
              </span>
            </h4>
            {w0.is_fcfs ? (
              <p className="fcfs-label"><span title="First-come, first-served">FCFS</span> &mdash; not bookable online</p>
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
                      onClick={() => track("book_click", {
                        facility_id: result.facility_id,
                  result_rank: rank ?? -1,
                  drive_minutes: result.estimated_drive_minutes ?? -1,
                  total_available_sites: result.total_available_sites,
                        name: result.name,
                        source: result.booking_system,
                        type: "site_window",
                        site: w.site_name,
                        nights: w.nights,
                        has_photo: result.image_urls?.length ? 1 : 0,
                      })}
                    >
                      {dayName} {fmtDate(w.start_date)} &rarr; {new Date(w.end_date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })} {fmtDate(w.end_date)} ({w.nights}n)
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

// ---------------------------------------------------------------------------
// ResultCard
// ---------------------------------------------------------------------------

/**
 * memo() is load-bearing here: these cards render in a list of up to 50 inside
 * the same component that owns the search input, so without it every keystroke
 * re-rendered all of them. memo only helps while the call site keeps prop
 * identities stable — hence `registerRef(index, el)` rather than an inline
 * `ref={el => ...}` closure, which would be a new function per card per render.
 */
export const ResultCard = memo(function ResultCard({
  result,
  index,
  view,
  searchDates,
  focused,
  registerRef,
  compareSelected,
  onToggleCompare,
  compareDisabled,
  onShowMap,
}: {
  result: SearchResponse["results"][0];
  index?: number;
  view: ResultsView;
  searchDates?: { start: string; end: string };
  focused?: boolean;
  registerRef?: (index: number, el: HTMLButtonElement | null) => void;
  compareSelected?: boolean;
  onToggleCompare?: (facilityId: string) => void;
  compareDisabled?: boolean;
  onShowMap?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  // The body is collapsed with grid-template-rows: 0fr, which hides it but
  // still builds, lays out and styles the whole subtree. SiteView emits one
  // anchor per window with no cap, so a 30-day search across 20 campgrounds
  // could put tens of thousands of invisible nodes in the document. Mount on
  // first expand, then keep it mounted so the open/close transition still runs.
  const [everExpanded, setEverExpanded] = useState(false);

  const handleHeaderRef = useCallback(
    (el: HTMLButtonElement | null) => {
      if (index !== undefined) registerRef?.(index, el);
    },
    [registerRef, index]
  );
  const cardRef = useRef<HTMLDivElement>(null);

  const hasPhoto = !!(result.image_urls && result.image_urls.length > 0);
  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      setEverExpanded(true);
      track("card_expand", {
        facility_id: result.facility_id,
        name: result.name,
        source: result.booking_system,
        has_photo: hasPhoto ? 1 : 0,
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

  const sourceLabel = SOURCE_LABELS[result.booking_system] || result.booking_system;
  const dateBlocks = groupByDateBlock(result.windows);
  const summaryText =
    view === "dates"
      ? `${result.total_available_sites} sites \u00b7 ${dateBlocks.length} opening${dateBlocks.length !== 1 ? "s" : ""}`
      : `${result.total_available_sites} sites \u00b7 ${result.windows.filter((w) => !w.is_fcfs).length} openings`;

  return (
    <div className={`result-card card-${result.booking_system}${focused ? " card-focused" : ""}`} ref={cardRef}>
      <div className="result-header-row">
        <button
          className="result-header"
          onClick={handleToggle}
          aria-expanded={expanded}
          type="button"
          ref={handleHeaderRef}
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
              {result.weather_temp_high_f != null && result.weather_temp_high_f > -900 && result.weather_temp_low_f != null && (
                <span className="weather-badge">
                  {result.weather_temp_high_f}°/{result.weather_temp_low_f}°F
                  {result.weather_precip_pct != null && result.weather_precip_pct >= 20 &&
                    ` · ${result.weather_precip_pct}% rain`}
                </span>
              )}
              {(result.tags || []).slice(0, 4).map((tag) => (
                <span key={tag} className="tag-badge">{tag}</span>
              ))}
            </h3>
            <p className="result-summary">
              {summaryText}
              {result.fcfs_sites > 0 && <>{" "}+ {result.fcfs_sites} <span title="First-come, first-served">FCFS</span></>}
            </p>
            {result.elevator_pitch && (
              <p className="result-pitch">{result.elevator_pitch}</p>
            )}
          </div>
          <span className="expand-icon" aria-hidden="true">{expanded ? <IconMinus className="icon-sm" /> : <IconPlus className="icon-sm" />}</span>
        </button>
        {onToggleCompare && (
          <button
            className={`compare-check${compareSelected ? " selected" : ""}`}
            onClick={() => onToggleCompare(result.facility_id)}
            disabled={compareDisabled && !compareSelected}
            title={compareSelected ? "Remove from comparison" : "Add to comparison"}
            aria-label={compareSelected ? "Remove from comparison" : "Add to comparison"}
            type="button"
          >
            {compareSelected ? "\u2713" : "vs"}
          </button>
        )}
      </div>

      <div className={`card-body${expanded ? " card-body-open" : ""}`}>
        <div className="card-body-inner">
          {everExpanded && (<>
          {expanded && (
            hasPhoto ? (
              <HeroPhoto
                urls={result.image_urls!}
                name={result.name}
                attribution={result.image_attribution ?? ""}
                facilityId={result.facility_id}
                source={result.booking_system}
              />
            ) : (
              <PostcardPlaceholder
                name={result.name}
                region={result.region ?? ""}
                state={result.state}
                tags={result.tags}
                bookingSystem={result.booking_system}
              />
            )
          )}
          {(result.description_rewrite || result.vibe) && (
            <p className="result-vibe">{result.description_rewrite || result.vibe}</p>
          )}
          {result.best_for && (
            <p className="result-best-for">Best for: {result.best_for}</p>
          )}
          {result.availability_url && (
            <div className="card-toolbar">
              <a
                href={result.availability_url}
                target="_blank"
                rel="noopener"
                className="book-link"
                onClick={() => track("book_click", {
                  facility_id: result.facility_id,
                  result_rank: index ?? -1,
                  drive_minutes: result.estimated_drive_minutes ?? -1,
                  total_available_sites: result.total_available_sites,
                  name: result.name,
                  source: result.booking_system,
                  type: "view_page",
                  has_photo: hasPhoto ? 1 : 0,
                })}
              >
                View on{" "}
                {result.booking_system === "wa_state"
                  ? "GoingToCamp"
                  : "Recreation.gov"}{" "}
                {"\u2197"}
              </a>
              {result.latitude && result.longitude && onShowMap && (
                <button type="button" className="map-link" onClick={onShowMap}>
                  See on map
                </button>
              )}
              {searchDates && (
                <WatchButton
                  facilityId={result.facility_id}
                  name={result.name}
                  startDate={searchDates.start}
                  endDate={searchDates.end}
                />
              )}
              <SaveToTripButton
                facilityId={result.facility_id}
                source={result.booking_system}
                name={result.name}
              />
            </div>
          )}
          {view === "dates" ? (
            <DateBlockView result={result} rank={index} />
          ) : (
            <SiteView result={result} rank={index} />
          )}
          </>)}
        </div>
      </div>
    </div>
  );
});
