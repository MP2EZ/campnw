import { useState } from "react";
import type { CampgroundResult, SearchParams } from "../api";
import { formatDriveTime } from "../lib/dates";
import { SOURCE_NAMES } from "../lib/sources";
import { IconBell } from "../icons";
import { fullGroupTitle, unavailability, unavailableText } from "./candidates";
import { remindStays, todayIso, watchStays } from "./watch";
import { useOpenWatch } from "./watchContext";

const ROW_LIMIT = 6;
export const FULL_GROUP_ID = "rv2-full";

const byDrive = (a: CampgroundResult, b: CampgroundResult) =>
  Number(!!a.boat_in) - Number(!!b.boat_in)
  || (a.estimated_drive_minutes ?? Infinity) - (b.estimated_drive_minutes ?? Infinity);

/**
 * "Full or not released yet" (D4): checked places with nothing to book on
 * the searched dates, closest first, each with what's in the way and the
 * alert that would help. Watch opens the Watch sheet (P3c), Remind me its
 * release-reminder mode (P3d). Outside results both are disabled stubs.
 */
export function FullGroup({ places, params, title = fullGroupTitle(places, params) }: {
  places: CampgroundResult[];
  params: SearchParams | null;
  title?: string;
}) {
  const [all, setAll] = useState(false);
  const openWatch = useOpenWatch();
  if (places.length === 0) return null;
  const today = todayIso();
  // Each row's alert: live Watch or Remind me inside results, a disabled stub
  // outside them, or none (not reservable, or no release date left).
  const rows = [...places].sort(byDrive).map((r) => {
    const { status, action } = unavailableText(unavailability(r, params), params);
    const live = !openWatch ? null
      : action === "Watch" ? (watchStays(r, params).length > 0 ? "watch" : null)
      : action === "Remind me" ? (remindStays(r, params, today).length > 0 ? "remind" : "none")
      : null;
    return { r, status, action, live };
  });
  const cut = rows.length > ROW_LIMIT + 1 ? ROW_LIMIT : rows.length;
  const shown = all ? rows : rows.slice(0, cut);
  const noteId = `${FULL_GROUP_ID}-note`;
  const watch = rows.some((x) => x.live === "watch");
  const remind = rows.some((x) => x.live === "remind");
  // Offer only the alerts the rows actually have.
  const offer = !openWatch
    ? rows.some((x) => x.action) && "Alerts for when a site frees up, or when booking opens, are coming soon."
    : watch && remind ? "Watch a place to hear when a site frees up, or get a reminder the morning booking opens."
    : watch ? "Watch a place to hear when a site frees up."
    : remind ? "Get a reminder the morning booking opens."
    : null;

  return (
    <section id={FULL_GROUP_ID} className="rv2-band" aria-labelledby={`${FULL_GROUP_ID}-h`}>
      <div className="rv2-band-head">
        <h2 id={`${FULL_GROUP_ID}-h`} className="rv2-band-title">{title}</h2>
        <span className="rv2-band-count">{places.length} place{places.length === 1 ? "" : "s"}</span>
        <span className="rv2-band-rule" aria-hidden="true" />
      </div>
      <p id={noteId} className="rv2-band-note">
        {title === "Nothing to book" ? "Nothing open on your dates." : "Nothing to book on your dates."}
        {offer && ` ${offer}`}
      </p>
      <ul className="rv2-full-list">
        {shown.map(({ r, status, action, live }) => {
          const source = SOURCE_NAMES[r.booking_system] ?? r.booking_system;
          const where = r.boat_in
            ? "Boat-in only"
            : r.estimated_drive_minutes != null ? `${formatDriveTime(r.estimated_drive_minutes)} drive` : null;
          return (
            <li key={r.facility_id} className="rv2-full-row">
              <div className="rv2-full-place">
                <h3 className="rv2-full-name">{r.name}</h3>
                <p className="rv2-full-meta">{[where, source].filter(Boolean).join(" · ")}</p>
              </div>
              <span className="rv2-full-status">{status}</span>
              {live === "watch" ? (
                <button type="button" className="rv2-full-action rv2-full-action--live"
                  aria-label={`Watch: ${r.name}`} onClick={() => openWatch?.(r, undefined, "full_group")}>
                  <IconBell className="rv2-icon" />Watch
                </button>
              ) : live === "remind" ? (
                <button type="button" className="rv2-full-action rv2-full-action--live"
                  aria-label={`Remind me: ${r.name}`} onClick={() => openWatch?.(r, undefined, "full_group", "remind")}>
                  <IconBell className="rv2-icon" />Remind me
                </button>
              ) : live === null && action && (
                <button type="button" className="rv2-full-action" aria-disabled="true"
                  aria-label={`${action}: ${r.name}`} aria-describedby={noteId}>
                  <IconBell className="rv2-icon" />{action}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {rows.length > cut && (
        <button type="button" className="rv2-band-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show ${rows.length - cut} more`}
        </button>
      )}
    </section>
  );
}
