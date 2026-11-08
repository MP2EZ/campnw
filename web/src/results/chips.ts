import type { CampgroundResult, SearchParams, Window } from "../api";
import { parseIsoDate } from "../lib/dates";

/**
 * Window chips (v1.48 D3): the stays a card offers, one chip per weekend (or
 * per block of the searched days), one for exact dates, or one per distinct
 * stay for a flexible range. Dates are nights, like a window's start/end.
 */
export type ChipStatus = "open" | "full" | "not_released";

export interface WindowChip {
  /** First and last night, YYYY-MM-DD. */
  start: string;
  end: string;
  /** "Fri 4 – Sun 6"; "Fri Jul 30 – Sun Aug 1" when the search spans months. */
  label: string;
  /** Sites with a bookable stay in this chip. */
  open: number;
  /** Of those, sites that fit the party and rig. Equals `open` until the `who` filter (P1c). */
  fit: number;
  /** Few enough to say "N left". */
  few: boolean;
  /** Only "open" so far: "full" and "not_released" need D4's candidate windows (P2c). */
  status: ChipStatus;
  /** The one site's booking page, else the campground's. */
  href: string | null;
}

export interface WindowChips {
  shown: WindowChip[];
  /** Behind a "+k more" button. */
  more: WindowChip[];
}

export const CHIP_LIMIT = 4;
export const FEW_LEFT = 5;

/** Python's weekday (0 = Monday), which `days_of_week` uses. */
const weekday = (iso: string) => (parseIsoDate(iso).getDay() + 6) % 7;

function addDays(iso: string, n: number): string {
  const d = parseIsoDate(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The searched days, or null when every day counts (no blocks to group by). */
function searchedDays(p: SearchParams | null): Set<number> | null {
  const days = new Set((p?.days_of_week ?? "").split(",").filter(Boolean).map(Number));
  return days.size > 0 && days.size < 7 ? days : null;
}

/** The run of searched days around `night`, inside the search range. */
function blockAround(night: string, days: Set<number>, p: SearchParams): [string, string] {
  let start = night;
  let end = night;
  const inRange = (d: string) => (!p.start_date || d >= p.start_date) && (!p.end_date || d <= p.end_date);
  for (let prev = addDays(start, -1); days.has(weekday(prev)) && inRange(prev); prev = addDays(prev, -1)) start = prev;
  for (let next = addDays(end, 1); days.has(weekday(next)) && inRange(next); next = addDays(next, 1)) end = next;
  return [start, end];
}

// Intl orders weekday + day as "4 Fri"; build the parts in the design's order.
const part = (d: Date, unit: "weekday" | "month") => d.toLocaleDateString("en-US", { [unit]: "short" });
const day = (d: Date, month: boolean) =>
  [part(d, "weekday"), month && part(d, "month"), d.getDate()].filter(Boolean).join(" ");

function chipLabel(start: string, end: string, withMonth: boolean): string {
  const s = parseIsoDate(start);
  const e = parseIsoDate(end);
  const newMonth = s.getMonth() !== e.getMonth();
  return `${day(s, withMonth || newMonth)} – ${day(e, newMonth)}`;
}

export function buildWindowChips(result: CampgroundResult, params: SearchParams | null): WindowChips {
  const days = searchedDays(params);
  const exact = params?.mode === "exact" && params.start_date && params.end_date;
  const groups = new Map<string, { start: string; end: string; sites: Map<string, Window> }>();

  for (const w of result.windows) {
    if (w.is_fcfs) continue;
    const [start, end] = exact
      ? [params.start_date, params.end_date]
      : days && params
        ? blockAround(w.start_date, days, params)
        : [w.start_date, w.end_date];
    const key = `${start}→${end}`;
    if (!groups.has(key)) groups.set(key, { start, end, sites: new Map() });
    const sites = groups.get(key)!.sites;
    if (!sites.has(w.campsite_id)) sites.set(w.campsite_id, w);
  }

  const withMonth = !!params?.start_date && !!params.end_date
    && params.start_date.slice(0, 7) !== params.end_date.slice(0, 7);
  const chips = [...groups.values()]
    .sort((a, b) => a.start.localeCompare(b.start))
    .map(({ start, end, sites }): WindowChip => {
      const label = chipLabel(start, end, withMonth);
      const open = sites.size;
      const only = open === 1 ? [...sites.values()][0].booking_url : null;
      return {
        start, end, label, open, fit: open, few: open <= FEW_LEFT,
        status: "open", href: only ?? result.availability_url,
      };
    });

  // Hiding a single chip behind "+1 more" saves nothing.
  const cut = chips.length > CHIP_LIMIT + 1 ? CHIP_LIMIT : chips.length;
  return { shown: chips.slice(0, cut), more: chips.slice(cut) };
}

/** "3 left" or "40 open": the word, not just the colour, says it's nearly gone. */
export function chipCountText({ open, few }: Pick<WindowChip, "open" | "few">): string {
  return few ? `${open} left` : `${open} open`;
}
