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
  const sorted = [...places].sort(byDrive);
  const cut = sorted.length > ROW_LIMIT + 1 ? ROW_LIMIT : sorted.length;
  const shown = all ? sorted : sorted.slice(0, cut);
  const noteId = `${FULL_GROUP_ID}-note`;
  const today = todayIso();

  return (
    <section id={FULL_GROUP_ID} className="rv2-band" aria-labelledby={`${FULL_GROUP_ID}-h`}>
      <div className="rv2-band-head">
        <h2 id={`${FULL_GROUP_ID}-h`} className="rv2-band-title">{title}</h2>
        <span className="rv2-band-count">{places.length} place{places.length === 1 ? "" : "s"}</span>
        <span className="rv2-band-rule" aria-hidden="true" />
      </div>
      <p id={noteId} className="rv2-band-note">
        {title === "Nothing to book" ? "Nothing open on your dates. " : "Nothing to book on your dates. "}
        {openWatch ? "Watch a place to hear when a site frees up, or get a reminder the morning booking opens."
          : "Alerts for when a site frees up, or when booking opens, are coming soon."}
      </p>
      <ul className="rv2-full-list">
        {shown.map((r) => {
          const { status, action } = unavailableText(unavailability(r, params), params);
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
              {action === "Watch" && openWatch && watchStays(r, params).length > 0 ? (
                <button type="button" className="rv2-full-action rv2-full-action--live"
                  aria-label={`Watch: ${r.name}`} onClick={() => openWatch(r, undefined, "full_group")}>
                  <IconBell className="rv2-icon" />Watch
                </button>
              ) : action === "Remind me" && openWatch ? (
                // No button when there's no release date left to remind on.
                remindStays(r, params, today).length > 0 && (
                  <button type="button" className="rv2-full-action rv2-full-action--live"
                    aria-label={`Remind me: ${r.name}`} onClick={() => openWatch(r, undefined, "full_group", "remind")}>
                    <IconBell className="rv2-icon" />Remind me
                  </button>
                )
              ) : action && (
                <button type="button" className="rv2-full-action" aria-disabled="true"
                  aria-label={`${action}: ${r.name}`} aria-describedby={noteId}>
                  <IconBell className="rv2-icon" />{action}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {sorted.length > cut && (
        <button type="button" className="rv2-band-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show ${sorted.length - cut} more`}
        </button>
      )}
    </section>
  );
}
