import type { CampgroundResult, SearchParams, SearchResponse } from "../api";
import { formatDateRange, parseIsoDate } from "../lib/dates";
import { SOURCE_NAMES } from "../lib/sources";
import {
  addDays, candidateStatus, candidateWindows, fullGroupTitle, nightsIn, searchedDays, unavailability,
} from "./candidates";
import { hours } from "./searchState";

/** The zero-results page (design: Zero.dc.html), from the checked places with nothing to book. */

export interface TimelineItem {
  /** "Jun 4 – 6", or "Arrive Tue Jun 1" for a flexible search. */
  label: string;
  /** When booking opens, YYYY-MM-DD. */
  opens: string;
}

const TIMELINE_LIMIT = 6;

/** When each searched weekend (or arrival) opens for booking: the earliest across places. */
export function releaseTimeline(places: CampgroundResult[], p: SearchParams | null): { items: TimelineItem[]; more: number } {
  const items: TimelineItem[] = [];
  for (const c of candidateWindows(p)) {
    const dates = places
      .map((r) => candidateStatus(r, c))
      .flatMap((s) => (s.status === "not_released" && s.releasesOn ? [s.releasesOn] : []))
      .sort();
    if (!dates.length) continue;
    const label = c.stay
      ? `Arrive ${parseIsoDate(c.start).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }).replace(",", "")}`
      : formatDateRange(c.start, c.end);
    items.push({ label, opens: dates[0] });
  }
  return { items: items.slice(0, TIMELINE_LIMIT), more: Math.max(0, items.length - TIMELINE_LIMIT) };
}

export interface SoonerOption {
  title: string;
  detail: string;
  params: SearchParams;
}

const daysBetween = (a: string, b: string) => nightsIn(a, b) - 1;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * "Or camp sooner": other searches worth one tap, each from data the search
 * already has. Released dates (the same search moved before the release
 * horizon), the backend's nearby dates with their counts, the other
 * booking systems, and the backend's own fixes (wider drive, any day).
 */
export function soonerOptions(
  results: SearchResponse, places: CampgroundResult[], p: SearchParams | null, today: string,
): SoonerOption[] {
  if (!p) return [];
  const out: SoonerOption[] = [];

  // A night that opens in d days has nights about d days earlier open now.
  // Month lengths make that ±2 days, so stop 3 short.
  let horizon: string | null = null;
  for (const r of places) {
    for (const range of r.not_released_ranges ?? []) {
      if (!range.releases_on || range.releases_on <= today) continue;
      const end = addDays(range.start, -daysBetween(today, range.releases_on) - 3);
      if (!horizon || end < horizon) horizon = end;
    }
  }
  if (horizon && p.start_date && p.end_date) {
    const start = addDays(horizon, -daysBetween(p.start_date, p.end_date));
    const first = start > today ? start : addDays(today, 1);
    if (first < horizon) {
      out.push({
        title: "Search released dates",
        detail: `${formatDateRange(first, horizon)}, already open for booking`,
        params: { ...p, start_date: first, end_date: horizon },
      });
    }
  }

  for (const s of results.date_suggestions ?? []) {
    if (s.campgrounds_with_availability <= 0) continue;
    out.push({
      title: formatDateRange(s.start_date, s.end_date),
      detail: `${plural(s.campgrounds_with_availability, "campground")} open · ${s.reason}`,
      params: { ...p, start_date: s.start_date, end_date: s.end_date },
    });
  }

  if (p.source) {
    out.push({
      title: "Include every booking system",
      detail: `This search only checked ${SOURCE_NAMES[p.source] ?? p.source}`,
      params: { ...p, source: undefined },
    });
  }

  for (const chip of results.action_chips ?? []) {
    const cp = chip.params as Record<string, unknown>;
    if (chip.action === "expand_radius") {
      // The backend labels these in minutes ("Expand to 120 min"); the Drive control uses hours.
      const minutes = typeof cp.max_drive_minutes === "number" ? cp.max_drive_minutes : undefined;
      out.push(minutes
        ? { title: `Drive up to ${hours(minutes)}`, detail: p.max_drive ? `Instead of ${hours(p.max_drive)}` : "A longer drive",
          params: { ...p, max_drive: minutes } }
        : { title: chip.label, detail: "Any distance", params: { ...p, max_drive: undefined } });
    } else if (chip.action === "drop_days") {
      out.push({ title: chip.label, detail: "Any night of the week", params: { ...p, days_of_week: undefined } });
    } else if (chip.action === "drop_tags") {
      out.push({ title: chip.label, detail: "Without your tag filters", params: { ...p, tags: undefined } });
    } else if (chip.action === "shift_dates" && typeof cp.start_date === "string" && typeof cp.end_date === "string") {
      out.push({ title: chip.label, detail: formatDateRange(cp.start_date, cp.end_date),
        params: { ...p, start_date: cp.start_date, end_date: cp.end_date } });
    }
  }
  return out;
}

/**
 * The zero page's group name. "Not released yet" only when every place is
 * waiting on a release; closed or full places keep the group's usual name.
 */
export function zeroGroupTitle(places: CampgroundResult[], p: SearchParams | null): string {
  return places.length > 0 && places.every((r) => unavailability(r, p).kind === "not_released")
    ? "Not released yet" : fullGroupTitle(places, p);
}

/**
 * The paragraph under the answer: full or not released (they need different
 * help), and which booking systems couldn't be checked, so a partial search
 * never reads as the whole picture.
 */
export function zeroLede(results: SearchResponse, places: CampgroundResult[], p: SearchParams | null): string {
  const parts: string[] = [];
  const kinds = places.map((r) => unavailability(r, p).kind);
  const n = places.length;
  const nyr = kinds.filter((k) => k === "not_released" || k === "mixed").length;
  const closed = kinds.filter((k) => k === "closed").length;
  const full = n - nyr - closed;
  const are = (k: number, one: string, many: string) => (k === 1 ? one : many);
  // The answer counts every campground checked, including ones whose check
  // failed, so a smaller count here says "of the N" rather than contradict it.
  const checked = results.campgrounds_checked;
  const counted = (noun: string) => (n < checked ? `${n} of the ${checked} ${noun}s` : `The ${n} ${noun}${n === 1 ? "" : "s"}`);
  if (n > 0 && nyr === n) {
    const systems = new Set(places.map((r) => r.booking_system));
    const source = systems.size === 1 ? `${SOURCE_NAMES[[...systems][0]] ?? ""} ` : "";
    const month = p?.start_date && p.end_date && p.start_date.slice(0, 7) === p.end_date.slice(0, 7)
      ? `${parseIsoDate(p.start_date).toLocaleDateString("en-US", { month: "long" })} ` : "";
    const what = searchedDays(p) && p?.mode !== "exact" ? `${month}weekends` : "dates";
    parts.push(`${counted(`${source}campground`)} checked ${are(n, "isn’t", "aren’t")} full.`
      + ` ${are(n, "Its", "Their")} ${what} just haven’t opened for booking.`);
  } else if (n > 0 && full === n) {
    parts.push(`${counted("campground")} checked ${are(n, "is", "are")} full on your dates.`);
  } else if (n > 0 && closed === n) {
    parts.push(`${counted("campground")} checked ${are(n, "isn’t", "aren’t")} taking reservations online`
      + ` for these dates: ${are(n, "it’s", "they’re")} closed, or first-come, first-served only.`);
  } else if (n > 0 && closed === 0) {
    parts.push(`${nyr} of the ${n} campgrounds with nothing to book ${are(nyr, "hasn’t", "haven’t")} released these dates yet.`
      + ` The other${full === 1 ? " is" : "s are"} full.`);
  } else if (n > 0) {
    const bits = [
      nyr && `${nyr} ${are(nyr, "hasn’t", "haven’t")} released these dates yet`,
      full && `${full} ${are(full, "is", "are")} full`,
      `${closed} ${are(closed, "isn’t", "aren’t")} taking reservations online`,
    ].filter(Boolean) as string[];
    const list = bits.length > 1 ? `${bits.slice(0, -1).join(", ")} and ${bits[bits.length - 1]}` : bits[0];
    parts.push(`Of the ${n} campgrounds with nothing to book, ${list}.`);
  }
  for (const source of new Set((results.warnings ?? []).map((w) => w.source))) {
    const name = SOURCE_NAMES[source] ?? "A booking system";
    parts.push(`${name} couldn’t be checked right now, so its parks may still have openings.`);
  }
  return parts.join(" ");
}
