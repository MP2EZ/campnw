import type { CampgroundResult, SearchParams } from "../api";
import { formatDateRange, parseIsoDate } from "../lib/dates";

/**
 * Candidate windows (v1.48 D4): the stays a search asked for, derived from
 * the search alone, so a campground can be shown as Full or Not released for
 * the windows it *didn't* return. Dates are nights, like a window's.
 */
export interface Candidate {
  start: string;
  end: string;
  /** A stay of exactly the searched nights (flexible searches), not a block of days. */
  stay: boolean;
}

/** Python's weekday (0 = Monday), which `days_of_week` uses. */
const weekday = (iso: string) => (parseIsoDate(iso).getDay() + 6) % 7;

export function addDays(iso: string, n: number): string {
  const d = parseIsoDate(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Nights from `start` to `end`, both included. */
export const nightsIn = (start: string, end: string) =>
  Math.round((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / 86_400_000) + 1;

/** The searched days, or null when every day counts (no blocks to group by). */
export function searchedDays(p: SearchParams | null): Set<number> | null {
  const days = new Set((p?.days_of_week ?? "").split(",").filter(Boolean).map(Number));
  return days.size > 0 && days.size < 7 ? days : null;
}

/** The run of searched days around `night`, inside the search range. */
export function blockAround(night: string, days: Set<number>, p: SearchParams): [string, string] {
  let start = night;
  let end = night;
  const inRange = (d: string) => (!p.start_date || d >= p.start_date) && (!p.end_date || d <= p.end_date);
  for (let prev = addDays(start, -1); days.has(weekday(prev)) && inRange(prev); prev = addDays(prev, -1)) start = prev;
  for (let next = addDays(end, 1); days.has(weekday(next)) && inRange(next); next = addDays(next, 1)) end = next;
  return [start, end];
}

export function candidateWindows(p: SearchParams | null): Candidate[] {
  if (!p?.start_date || !p.end_date || p.end_date < p.start_date) return [];
  if (p.mode === "exact") return [{ start: p.start_date, end: p.end_date, stay: false }];
  const nights = p.nights || 2;
  const days = searchedDays(p);
  const out: Candidate[] = [];
  if (!days) {
    for (let a = p.start_date; nightsIn(a, p.end_date) >= nights; a = addDays(a, 1)) {
      out.push({ start: a, end: addDays(a, nights - 1), stay: true });
    }
    return out;
  }
  for (let d = p.start_date; d <= p.end_date; d = addDays(d, 1)) {
    if (!days.has(weekday(d))) continue;
    const [start, end] = blockAround(d, days, p);
    // A block too short for the stay can't be booked by anyone.
    if (nightsIn(start, end) >= nights) out.push({ start, end, stay: false });
    d = end;
  }
  return out;
}

export type CandidateStatus =
  | { status: "open" }
  | { status: "full" }
  | { status: "closed" }
  | { status: "not_released"; releasesOn: string | null };

export function candidateStatus(r: CampgroundResult, c: Candidate): CandidateStatus {
  const bookable = r.windows.filter((w) => !w.is_fcfs);
  const open = c.stay
    ? bookable.some((w) => w.start_date <= c.start && w.end_date >= c.end)
    : bookable.some((w) => w.start_date <= c.end && w.end_date >= c.start);
  if (open) return { status: "open" };

  // The candidate's first unreleased night, and when it opens (night N of a
  // range opens N days after the range's first night).
  let first: { night: string; releasesOn: string | null } | null = null;
  for (const range of r.not_released_ranges ?? []) {
    if (range.end < c.start || range.start > c.end) continue;
    const night = range.start > c.start ? range.start : c.start;
    if (first && first.night <= night) continue;
    const releasesOn = range.releases_on && addDays(range.releases_on, nightsIn(range.start, night) - 1);
    first = { night, releasesOn };
  }
  if (first) return { status: "not_released", releasesOn: first.releasesOn };
  // Not reservable: every night closed, first-come only, or without data.
  // Any night someone could have booked makes it full.
  const closed = (r.closed_ranges ?? []).reduce((n, x) => {
    const s = x.start > c.start ? x.start : c.start;
    const e = x.end < c.end ? x.end : c.end;
    return s <= e ? n + nightsIn(s, e) : n;
  }, 0);
  return closed >= nightsIn(c.start, c.end) ? { status: "closed" } : { status: "full" };
}

export interface Unavailability {
  kind: "full" | "not_released" | "closed" | "mixed";
  full: number;
  notReleased: number;
  closed: number;
  /** The one candidate, when the search has only one. */
  only: Candidate | null;
  releasesFrom: string | null;
  releasesThrough: string | null;
}

/** A campground with nothing to book: how many candidates are full, how many not released, and when they open. */
export function unavailability(r: CampgroundResult, p: SearchParams | null): Unavailability {
  const candidates = candidateWindows(p);
  let full = 0;
  let closed = 0;
  const dates: string[] = [];
  let notReleased = 0;
  for (const c of candidates) {
    const s = candidateStatus(r, c);
    if (s.status === "full") full++;
    if (s.status === "closed") closed++;
    if (s.status === "not_released") {
      notReleased++;
      if (s.releasesOn) dates.push(s.releasesOn);
    }
  }
  dates.sort();
  return {
    kind: [full, notReleased, closed].filter(Boolean).length > 1 ? "mixed"
      : notReleased ? "not_released" : closed ? "closed" : "full",
    full,
    notReleased,
    closed,
    only: candidates.length === 1 ? candidates[0] : null,
    releasesFrom: dates[0] ?? null,
    releasesThrough: dates[dates.length - 1] ?? null,
  };
}

const span = (a: string, b: string) =>
  a === b ? parseIsoDate(a).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : formatDateRange(a, b);

/** "June" when the search is within one calendar month, else null. */
function oneMonth(p: SearchParams | null): string | null {
  if (!p?.start_date || !p.end_date || p.start_date.slice(0, 7) !== p.end_date.slice(0, 7)) return null;
  return parseIsoDate(p.start_date).toLocaleDateString("en-US", { month: "long" });
}

/**
 * The status pill and action for a row in "Full or not released yet":
 * "Full all 4 weekends" · Watch, "June opens Dec 4 – 25" · Remind me, and
 * no action for places not taking reservations at all.
 */
export function unavailableText(u: Unavailability, p: SearchParams | null): {
  status: string;
  action: "Watch" | "Remind me" | null;
} {
  const weekends = !!searchedDays(p) && p?.mode !== "exact";
  const opens = u.releasesFrom && u.releasesThrough ? span(u.releasesFrom, u.releasesThrough) : null;
  if (u.kind === "full") {
    if (!weekends) return { status: "Full on your dates", action: "Watch" };
    if (u.only) return { status: `Full ${formatDateRange(u.only.start, u.only.end)}`, action: "Watch" };
    return { status: `Full all ${u.full} weekends`, action: "Watch" };
  }
  if (u.kind === "closed") {
    return { status: weekends ? "Not reservable these weekends" : "Not reservable on your dates", action: null };
  }
  if (u.kind === "not_released") {
    if (!opens) return { status: "Not released yet", action: "Remind me" };
    const month = oneMonth(p);
    return { status: month ? `${month} opens ${opens}` : `Opens ${opens}`, action: "Remind me" };
  }
  const action = u.notReleased ? "Remind me" : "Watch";
  const nyr = opens ? `open ${opens}` : "not released yet";
  if (!weekends) {
    const first = u.full ? "full" : "not reservable";
    return { status: u.notReleased ? `Partly ${first} · rest ${opens ? `opens ${opens}` : "not released yet"}`
      : "Partly full, partly not reservable", action };
  }
  const parts: [number, string][] = [];
  if (u.full) parts.push([u.full, "full"]);
  if (u.closed) parts.push([u.closed, "not reservable"]);
  if (u.notReleased) parts.push([u.notReleased, nyr]);
  const [[n, what], ...rest] = parts;
  return {
    status: [`${n} weekend${n === 1 ? "" : "s"} ${what}`, ...rest.map(([k, w]) => `${k} ${w}`)].join(" · "),
    action,
  };
}

/**
 * The group's name, true to what's in it: the design's "Full or not released
 * yet", or "Nothing to book" once some places aren't taking reservations.
 */
export function fullGroupTitle(places: CampgroundResult[], params: SearchParams | null): string {
  const closed = places.some((r) => {
    const u = unavailability(r, params);
    return u.kind === "closed" || u.closed > 0;
  });
  return closed ? "Nothing to book" : "Full or not released yet";
}
