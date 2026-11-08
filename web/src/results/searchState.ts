import type { SearchParams } from "../api";
import { formatDateRange, parseIsoDate } from "../lib/dates";
import { addDays } from "./candidates";

/**
 * The v2 search bar's state (v1.48 P3a) and its two pure mappings: to the
 * SearchParams that `handleSearch` runs and writes to the URL, and back from
 * them (a shared link, Back, or what the plain-language parser understood).
 */
export type Equipment = "tent" | "van" | "trailer";

export type When =
  | { kind: "this-weekend" }
  | { kind: "next-weekend" }
  /** YYYY-MM */
  | { kind: "month"; month: string }
  /** Arrival and checkout. */
  | { kind: "exact"; start: string; end: string }
  /** A flexible range that isn't one of the presets (from a link or the parser). Nights. */
  | { kind: "range"; start: string; end: string };

export interface BarState {
  /** Drive-from key, e.g. "seattle"; "" for none. */
  from: string;
  /** A campground name; "" for none. */
  name: string;
  when: When;
  /** `days_of_week` (0 = Monday); "" for any day. Not used for exact dates. */
  days: string;
  nights: number;
  people: number;
  equipment: Equipment | null;
  /** Feet; trailers only. */
  rigLength: number | null;
  /** Minutes; null for any distance. */
  maxDrive: number | null;
}

export const WEEKEND = "4,5,6";
export const LONG_WEEKEND = "3,4,5,6";
export const WEEKDAYS = "0,1,2,3,4";

export const DEFAULT_BAR: BarState = {
  from: "seattle",
  name: "",
  when: { kind: "next-weekend" },
  days: WEEKEND,
  nights: 2,
  people: 2,
  equipment: null,
  rigLength: null,
  maxDrive: null,
};

export const DRIVE_FROM: ReadonlyArray<[key: string, label: string]> = [
  ["seattle", "Seattle"], ["bellevue", "Bellevue"], ["portland", "Portland"],
  ["spokane", "Spokane"], ["bellingham", "Bellingham"], ["bend", "Bend, OR"],
  ["bozeman", "Bozeman, MT"], ["missoula", "Missoula, MT"], ["jackson", "Jackson, WY"],
  ["sacramento", "Sacramento, CA"], ["reno", "Reno, NV"], ["moscow", "Moscow, ID"],
];

const EQUIPMENT: Record<Equipment, string> = { tent: "Tent", van: "Van", trailer: "Trailer" };
const isEquipment = (v: unknown): v is Equipment => typeof v === "string" && v in EQUIPMENT;

type Range = { start: string; end: string };

/** Python weekday, 0 = Monday. */
const weekday = (iso: string) => (parseIsoDate(iso).getDay() + 6) % 7;

/** The Fri–Sun nights of this weekend, from today if it has started. */
export function thisWeekend(today: string): Range {
  const wd = weekday(today);
  if (wd === 4 || wd === 5) return { start: today, end: addDays(today, 6 - wd) };
  const fri = addDays(today, (4 - wd + 7) % 7);
  return { start: fri, end: addDays(fri, 2) };
}

export function nextWeekend(today: string): Range {
  const { end } = thisWeekend(today);
  return { start: addDays(end, 5), end: addDays(end, 7) };
}

/**
 * The current month and the eight after it, as YYYY-MM: WA State Parks book 9
 * months out. `selected` is added when it's further out, so a shared link's
 * month still shows as chosen.
 */
export function monthOptions(today: string, selected?: string): string[] {
  const d = parseIsoDate(today);
  const months = Array.from({ length: 9 }, (_, i) => {
    const m = new Date(d.getFullYear(), d.getMonth() + i, 1);
    return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}`;
  });
  return selected && selected > months[months.length - 1] ? [...months, selected] : months;
}

export function monthRange(month: string, today: string): Range {
  const [y, m] = month.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  const first = `${month}-01`;
  return { start: today > first ? today : first, end: `${month}-${String(last).padStart(2, "0")}` };
}

export function monthName(month: string, style: "long" | "short" = "long"): string {
  return parseIsoDate(`${month}-01`).toLocaleDateString("en-US", { month: style });
}

const nightsBetween = (start: string, end: string) =>
  Math.max(1, Math.round((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / 86_400_000));

function dates(when: When, today: string): Range {
  switch (when.kind) {
    case "this-weekend": return thisWeekend(today);
    case "next-weekend": return nextWeekend(today);
    case "month": return monthRange(when.month, today);
    default: return { start: when.start, end: when.end };
  }
}

/**
 * The search the bar describes. `keep` carries the filters the bar doesn't
 * edit (state, tags, source…) over from the current search; a plain-language
 * `q` isn't kept, since the bar's own fields now say what to search.
 *
 * A campground name drops the drive cap: someone who names a place wants that
 * place, however far it is (plan P3a).
 */
export function barToParams(bar: BarState, today: string, keep?: SearchParams | null): SearchParams {
  const { start, end } = dates(bar.when, today);
  const exact = bar.when.kind === "exact";
  const p: SearchParams = {
    start_date: start,
    end_date: end,
    mode: exact ? "exact" : "find",
    nights: exact ? nightsBetween(start, end) : bar.nights,
  };
  if (!exact && bar.days) p.days_of_week = bar.days;
  if (bar.from) p.from_location = bar.from;
  if (bar.name) p.name = bar.name;
  else if (bar.maxDrive) p.max_drive = bar.maxDrive;
  p.people = bar.people;
  if (bar.equipment) p.equipment = bar.equipment;
  if (bar.equipment === "trailer" && bar.rigLength) p.rig_length = bar.rigLength;
  if (keep) {
    for (const k of ["state", "tags", "source", "no_groups", "include_fcfs", "limit"] as const) {
      if (keep[k] !== undefined) (p as unknown as Record<string, unknown>)[k] = keep[k];
    }
  }
  return p;
}

function whenFrom(p: SearchParams, today: string): When {
  const { start_date: start, end_date: end } = p;
  if (p.mode === "exact") return { kind: "exact", start, end };
  const same = (r: Range) => r.start === start && r.end === end;
  if (same(thisWeekend(today))) return { kind: "this-weekend" };
  if (same(nextWeekend(today))) return { kind: "next-weekend" };
  const month = start.slice(0, 7);
  if (end.slice(0, 7) === month && same(monthRange(month, today))) return { kind: "month", month };
  return { kind: "range", start, end };
}

/** The bar for a search; the defaults before there is one. */
export function paramsToBar(p: SearchParams | null, today: string): BarState {
  if (!p?.start_date || !p.end_date) return DEFAULT_BAR;
  const equipment = isEquipment(p.equipment) ? p.equipment : null;
  return {
    from: p.from_location ?? "",
    name: p.name ?? "",
    when: whenFrom(p, today),
    days: p.mode === "exact" ? DEFAULT_BAR.days : (p.days_of_week ?? ""),
    nights: p.nights ?? DEFAULT_BAR.nights,
    people: p.people ?? DEFAULT_BAR.people,
    equipment,
    rigLength: equipment === "trailer" ? (p.rig_length ?? null) : null,
    maxDrive: p.max_drive ?? null,
  };
}

// ─── Segment labels ──────────────────────────────────────────────────

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function fromLabel(from: string): string {
  const known = DRIVE_FROM.find(([k]) => k === from.toLowerCase());
  if (known) return known[1].split(",")[0];
  return from;
}

export function whereLabel(bar: BarState): string {
  if (bar.name) return bar.name;
  return bar.from ? `Near ${fromLabel(bar.from)}` : "Anywhere";
}

const DAY_WORDS: Record<string, string> = {
  [WEEKEND]: "Weekends", [LONG_WEEKEND]: "Long weekends", [WEEKDAYS]: "Weekdays",
};
const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** "Weekends", "Mon/Wed", or "" for any day. */
function daysWord(days: string): string {
  if (!days) return "";
  return DAY_WORDS[days] ?? days.split(",").map((d) => DAY_SHORT[Number(d)]).join("/");
}

/** The When segment without nights: "Weekends in June", "This weekend", "Jul 2 – 5". */
export function whenTitle(bar: BarState): string {
  const { when } = bar;
  if (when.kind === "this-weekend") return "This weekend";
  if (when.kind === "next-weekend") return "Next weekend";
  if (when.kind === "exact") return formatDateRange(when.start, when.end);
  const days = daysWord(bar.days);
  if (when.kind === "month") {
    const month = monthName(when.month);
    return days ? `${days} in ${month}` : month;
  }
  const range = formatDateRange(when.start, when.end);
  return days ? `${days}, ${range}` : range;
}

export function whenLabel(bar: BarState): string {
  const nights = bar.when.kind === "exact" ? nightsBetween(bar.when.start, bar.when.end) : bar.nights;
  return `${whenTitle(bar)} · ${plural(nights, "night")}`;
}

function rig(bar: BarState): string {
  if (!bar.equipment) return "";
  if (bar.equipment === "trailer" && bar.rigLength) return `${bar.rigLength}′ trailer`;
  return EQUIPMENT[bar.equipment];
}

export function whoLabel(bar: BarState): string {
  const people = plural(bar.people, "person", "people");
  const r = rig(bar);
  return r ? `${people} · ${r}` : people;
}

function hours(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m}` : `${h} h`;
}

export function driveLabel(bar: BarState): string {
  if (bar.name || !bar.maxDrive) return "Any distance";
  return `Up to ${hours(bar.maxDrive)}`;
}

/** The mobile bar's two lines. */
export function compactLabel(bar: BarState): { title: string; detail: string } {
  const r = rig(bar);
  const who = plural(bar.people, "person", "people") + (r ? `, ${r.toLowerCase()}` : "");
  const parts = [whereLabel(bar), who];
  if (!bar.name && bar.maxDrive) parts.push(`up to ${hours(bar.maxDrive)}`);
  return { title: whenTitle(bar), detail: parts.join(" · ") };
}
