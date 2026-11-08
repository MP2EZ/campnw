import type { CampgroundResult, SearchParams, Window } from "../api";
import { parseIsoDate } from "../lib/dates";
import { addDays, blockAround, candidateStatus, candidateWindows, nightsIn, searchedDays } from "./candidates";

/**
 * Window chips (v1.48 D3): the stays a card offers, one chip per weekend (or
 * per block of the searched days), one for exact dates, or one per arrival
 * date for a flexible range ("stay chips": the searched number of nights from
 * that arrival). Dates are nights, like a window's start/end.
 */
export type ChipStatus = "open" | "full" | "not_released" | "closed";

export interface WindowChip {
  /** First and last night, YYYY-MM-DD. */
  start: string;
  end: string;
  /**
   * Blocks: their nights, "Fri 4 – Sun 6"; "Fri Jul 30 – Sun Aug 1" when the
   * search spans months. Stays: arrival to checkout, "Tue 8 – Thu 10".
   */
  label: string;
  /** Sites with a bookable stay in this chip. */
  open: number;
  /** Of those, sites that fit the party and rig. Equals `open` until the `who` filter (P1c). */
  fit: number;
  /** Few enough to say "N left". */
  few: boolean;
  /**
   * The shortest stay every counted site offers, when some can't take the
   * whole chip (a weekend where one site has only Friday): "3 left · 1+
   * nights". Null when every site has every night.
   */
  minNights: number | null;
  /**
   * Weekend and day-filter searches also list the blocks with nothing open
   * (D4): "full", or "not_released" with when booking opens.
   */
  status: ChipStatus;
  /** When a not-released chip opens for booking; null if unknown or not that status. */
  releasesOn: string | null;
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

/** Longest run of consecutive nights the spans cover. */
function longestRun(spans: [string, string][]): number {
  let best = 0;
  let run: [string, string] | null = null;
  for (const [s, e] of [...spans].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (run && s <= addDays(run[1], 1)) {
      if (e > run[1]) run[1] = e;
    } else {
      run = [s, e];
    }
    best = Math.max(best, nightsIn(run[0], run[1]));
  }
  return best;
}

interface Group {
  start: string;
  end: string;
  stay: boolean;
  /** Per site: its first window (for the booking link) and the nights it covers here. */
  sites: Map<string, { window: Window; spans: [string, string][] }>;
}

export function buildWindowChips(result: CampgroundResult, params: SearchParams | null): WindowChips {
  const days = searchedDays(params);
  const exact = params?.mode === "exact" && params.start_date && params.end_date;
  const windows = result.windows.filter((w) => !w.is_fcfs);
  // Flexible ranges: one chip per arrival for the searched stay. Without
  // params there's no stay length, so the shortest window stands in.
  const stayNights = params?.nights
    || Math.min(...windows.map((w) => nightsIn(w.start_date, w.end_date)));
  const groups = new Map<string, Group>();
  const add = (start: string, end: string, w: Window, span: [string, string], stay = false) => {
    const key = `${start}→${end}`;
    if (!groups.has(key)) groups.set(key, { start, end, stay, sites: new Map() });
    const sites = groups.get(key)!.sites;
    if (!sites.has(w.campsite_id)) sites.set(w.campsite_id, { window: w, spans: [] });
    sites.get(w.campsite_id)!.spans.push(span);
  };

  for (const w of windows) {
    if (exact || (days && params)) {
      const [start, end] = exact ? [params.start_date, params.end_date] : blockAround(w.start_date, days!, params!);
      const clipped: [string, string] = [w.start_date > start ? w.start_date : start, w.end_date < end ? w.end_date : end];
      add(start, end, w, clipped);
      continue;
    }
    for (let a = w.start_date; nightsIn(a, w.end_date) >= stayNights; a = addDays(a, 1)) {
      const last = addDays(a, stayNights - 1);
      add(a, last, w, [a, last], true);
    }
  }

  const withMonth = !!params?.start_date && !!params.end_date
    && params.start_date.slice(0, 7) !== params.end_date.slice(0, 7);
  const chips = [...groups.values()]
    .sort((a, b) => a.start.localeCompare(b.start))
    .map(({ start, end, stay, sites }): WindowChip => {
      const label = stay ? chipLabel(start, addDays(end, 1), withMonth) : chipLabel(start, end, withMonth);
      const open = sites.size;
      const only = open === 1 ? [...sites.values()][0].window.booking_url : null;
      const shortest = Math.min(...[...sites.values()].map((s) => longestRun(s.spans)));
      return {
        start, end, label, open, fit: open, few: open <= FEW_LEFT,
        // Two nights is a whole weekend, so only a shorter shortest stay is said.
        minNights: shortest < Math.min(nightsIn(start, end), 2) ? shortest : null,
        status: "open", releasesOn: null, href: only ?? result.availability_url,
      };
    });

  // Blocks of searched days with nothing open: full or not released yet.
  if (days && !exact) {
    const open = new Set(chips.map((c) => c.start));
    for (const c of candidateWindows(params)) {
      if (open.has(c.start)) continue;
      const s = candidateStatus(result, c);
      if (s.status === "open") continue;
      chips.push({
        start: c.start, end: c.end, label: chipLabel(c.start, c.end, withMonth), open: 0, fit: 0, few: false,
        minNights: null, status: s.status, releasesOn: s.status === "not_released" ? s.releasesOn : null, href: null,
      });
    }
    chips.sort((a, b) => a.start.localeCompare(b.start));
  }

  // Hiding a single chip behind "+1 more" saves nothing.
  const cut = chips.length > CHIP_LIMIT + 1 ? CHIP_LIMIT : chips.length;
  return { shown: chips.slice(0, cut), more: chips.slice(cut) };
}

/**
 * "3 left" or "40 open": the word, not just the colour, says it's nearly
 * gone. "· 1+ nights" when some site has only one night of the chip.
 * "Full", "Opens Dec 18" and "Not reservable" for blocks with nothing open.
 */
export function chipCountText(
  { open, few, minNights, status, releasesOn }: Pick<WindowChip, "open" | "few" | "minNights" | "status" | "releasesOn">,
): string {
  if (status === "full") return "Full";
  if (status === "closed") return "Not reservable";
  if (status === "not_released") {
    return releasesOn
      ? `Opens ${parseIsoDate(releasesOn).toLocaleDateString("en-US", { month: "short", day: "numeric" })}`
      : "Not released yet";
  }
  const count = few ? `${open} left` : `${open} open`;
  return minNights ? `${count} · ${minNights}+ nights` : count;
}
