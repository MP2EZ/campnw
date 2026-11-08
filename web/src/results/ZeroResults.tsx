import { useEffect } from "react";
import { track, type CampgroundResult, type SearchParams, type SearchResponse } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { parseIsoDate } from "../lib/dates";
import { IconBell } from "../icons";
import { searchedDays, unavailability } from "./candidates";
import { FullGroup } from "./FullGroup";
import { releaseTimeline, soonerOptions, zeroLede } from "./zero";

interface Props {
  results: SearchResponse;
  places: CampgroundResult[];
  params: SearchParams | null;
  onSearch: (params: SearchParams, mode: SearchMode) => void;
  searchId?: string;
}

const isoToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const opensLabel = (iso: string) =>
  parseIsoDate(iso).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

/**
 * Nothing open (design: Zero.dc.html). Says whether places are full or not
 * released yet, when booking opens, other searches worth one tap, and which
 * booking systems couldn't be checked. Release reminders are a stub until P3d.
 */
export function ZeroResults({ results, places, params, onSearch, searchId }: Props) {
  const timeline = releaseTimeline(places, params);
  const options = soonerOptions(results, places, params, isoToday());
  const lede = zeroLede(results, places, params);
  const allNyr = places.length > 0 && places.every((r) => unavailability(r, params).kind !== "full");
  // Recreation.gov releases at 7 am PT (search/release.py); WA's time is unverified.
  const at = places.length > 0 && places.every((r) => r.booking_system === "recgov") ? "7:00 am PT" : null;
  const unit = params?.mode === "exact" ? "your dates open" : searchedDays(params) ? "each weekend opens" : "each arrival opens";

  useEffect(() => {
    track("zero_state_shown", {
      search_id: searchId || "",
      has_diagnosis: results.diagnosis ? 1 : 0,
      binding_constraint: results.diagnosis?.binding_constraint || "",
      date_suggestion_count: results.date_suggestions?.length ?? 0,
      action_chip_count: results.action_chips?.length ?? 0,
      ui_version: "v2",
    });
    // Once per zero page, keyed on the search that produced it.
  }, [searchId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="rv2-zero">
      {lede && <p className="rv2-zero-lede">{lede}</p>}

      {timeline.items.length > 0 && (
        <section className="rv2-zero-card" aria-labelledby="rv2-release-h">
          <h2 id="rv2-release-h" className="rv2-zero-title">When {unit}</h2>
          <ol className="rv2-release-list">
            {timeline.items.map((t) => (
              <li key={t.label} className="rv2-release-item">
                <span className="rv2-release-what">{t.label}</span>
                <span className="rv2-release-when">{opensLabel(t.opens)}</span>
                {at && <span className="rv2-release-what">{at}</span>}
              </li>
            ))}
          </ol>
          {timeline.more > 0 && <p className="rv2-zero-note">And {timeline.more} more, a day apart.</p>}
          <div className="rv2-zero-remind">
            <button type="button" className="rv2-zero-remind-btn" aria-disabled="true" aria-describedby="rv2-remind-note">
              <IconBell className="rv2-icon" />Remind me on release mornings
            </button>
            <p id="rv2-remind-note" className="rv2-zero-note">Release-morning reminders are coming soon.</p>
          </div>
        </section>
      )}

      {options.length > 0 && (
        <section className="rv2-zero-try" aria-labelledby="rv2-sooner-h">
          <h2 id="rv2-sooner-h" className="rv2-zero-title">{timeline.items.length > 0 ? "Or camp sooner" : "Try instead"}</h2>
          <ul className="rv2-sooner-grid">
            {options.map((o) => (
              <li key={o.title}>
                <button type="button" className="rv2-sooner" onClick={() => {
                  track("zero_state_recovery_clicked", { search_id: searchId || "", chip_type: "v2_option", chip_label: o.title });
                  onSearch(o.params, "find");
                }}>
                  <span className="rv2-sooner-title">{o.title}</span>{" "}
                  <span className="rv2-sooner-detail">{o.detail}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <FullGroup places={places} params={params} title={allNyr ? "Not released yet" : undefined} />
    </div>
  );
}
