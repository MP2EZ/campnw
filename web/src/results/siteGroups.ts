import type { CampgroundResult, SearchParams, Window } from "../api";
import { addDays, nightsIn, searchedDays } from "./candidates";
import type { WindowChip } from "./chips";
import { NOT_LISTED } from "./fit";
import { stayUrl, type HandoffSite } from "./handoff";

/**
 * The site panel (v1.48 P3b, D7): the open sites behind one chip, grouped by
 * type, from the windows already in the search payload. Dates are nights,
 * like a window's.
 */
export type SiteKind = "tent" | "rv" | "walk_in" | "group" | "cabin" | "unlisted";

export interface PanelSite extends HandoffSite {
  id: string;
  kind: SiteKind;
  /** "Tent, van or RV up to 30′", or "Site types not listed yet". */
  fit: string;
  /** Null when the booking system doesn't state it. */
  people: number | null;
  hookups: boolean;
  walkIn: boolean;
  /** The nights it has when they're only part of the chip; null when it has all of them. */
  part: { start: string; end: string } | null;
  href: string | null;
}

export interface PanelGroup {
  kind: SiteKind;
  title: string;
  sites: PanelSite[];
}

const TITLES: Record<SiteKind, string> = {
  tent: "Tent and van sites",
  rv: "RV and trailer sites",
  walk_in: "Walk-in sites",
  group: "Group sites",
  cabin: "Cabins and yurts",
  unlisted: NOT_LISTED,
};
const ORDER: SiteKind[] = ["tent", "rv", "walk_in", "group", "cabin", "unlisted"];

function kindOf(w: Window): SiteKind {
  const type = w.campsite_type.toUpperCase();
  if (type.includes("GROUP")) return "group";
  if (/CABIN|YURT|LODGE|SHELTER|HUT|TEPEE|TEEPEE|TIPI/.test(type)) return "cabin";
  if (w.walk_in) return "walk_in";
  if (w.fits_rv) return "rv";
  if (w.fits_tent || w.fits_van) return "tent";
  return "unlisted";
}

/**
 * What one site takes. Only what it's known to take is listed: null is
 * unknown, never "doesn't fit". "only" is said when every other type is
 * known not to fit.
 */
export function siteFit(w: Window): string {
  const parts: string[] = [];
  if (w.fits_tent) parts.push("tent");
  if (w.fits_van) parts.push("van");
  if (w.fits_rv) parts.push(w.max_rv_ft != null ? `RV up to ${w.max_rv_ft}′` : "RV");
  if (!parts.length) return NOT_LISTED;
  const list = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} or ${parts[parts.length - 1]}`;
  const text = list[0].toUpperCase() + list.slice(1);
  const others = [w.fits_tent, w.fits_van, w.fits_rv].filter((f) => !f);
  return parts.length === 1 && others.every((f) => f === false) ? `${text} only` : text;
}

/** Longest run of consecutive nights the spans cover (earliest on a tie). */
function longestSpan(spans: [string, string][]): [string, string] {
  let best: [string, string] = spans[0];
  let run: [string, string] | null = null;
  for (const [s, e] of [...spans].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (run && s <= addDays(run[1], 1)) {
      if (e > run[1]) run[1] = e;
    } else {
      run = [s, e];
    }
    if (nightsIn(run[0], run[1]) > nightsIn(best[0], best[1])) best = [run[0], run[1]];
  }
  return best;
}

/** "Loop F" for a bare letter; empty when the loop is just the campground's name. */
function loopLabel(loop: string, campground: string): string {
  const l = loop.trim();
  if (!l || l.toLowerCase() === campground.toLowerCase()) return "";
  return /loop/i.test(l) ? l : `Loop ${l}`;
}

const byName = (a: PanelSite, b: PanelSite) =>
  Number(!!a.part) - Number(!!b.part)
  || a.loop.localeCompare(b.loop, undefined, { numeric: true })
  || a.name.localeCompare(b.name, undefined, { numeric: true });

export function panelGroups(
  result: CampgroundResult,
  chip: Pick<WindowChip, "start" | "end">,
  params: SearchParams | null,
): PanelGroup[] {
  // Same rule as buildWindowChips: blocks (weekends, exact dates) count any
  // nights inside the chip; flexible stays need the whole stay.
  const blocks = (params?.mode === "exact" && !!params.start_date && !!params.end_date) || !!searchedDays(params);
  const sites = new Map<string, { windows: Window[]; spans: [string, string][] }>();
  for (const w of result.windows) {
    if (w.is_fcfs || w.end_date < chip.start || w.start_date > chip.end) continue;
    if (!blocks && (w.start_date > chip.start || w.end_date < chip.end)) continue;
    const span: [string, string] = [w.start_date > chip.start ? w.start_date : chip.start,
      w.end_date < chip.end ? w.end_date : chip.end];
    if (!sites.has(w.campsite_id)) sites.set(w.campsite_id, { windows: [], spans: [] });
    const site = sites.get(w.campsite_id)!;
    site.windows.push(w);
    site.spans.push(span);
  }

  const groups = new Map<SiteKind, PanelSite[]>();
  for (const [id, { windows, spans }] of sites) {
    const [start, end] = longestSpan(spans);
    const w = windows.find((x) => x.start_date <= start && x.end_date >= start) ?? windows[0];
    const own = stayUrl(w.booking_url, start, end);
    const kind = kindOf(w);
    if (!groups.has(kind)) groups.set(kind, []);
    groups.get(kind)!.push({
      id, name: w.site_name, loop: loopLabel(w.loop, result.name), kind, fit: siteFit(w),
      people: w.max_people_known === false ? null : w.max_people,
      hookups: !!w.hookups, walkIn: !!w.walk_in, start, end,
      part: start === chip.start && end === chip.end ? null : { start, end },
      href: own ?? stayUrl(result.availability_url, start, end),
      perSite: !!own,
    });
  }

  const order = params?.equipment === "trailer" ? ["rv", ...ORDER.filter((k) => k !== "rv")] as SiteKind[] : ORDER;
  return order.filter((k) => groups.has(k))
    .map((kind) => ({ kind, title: TITLES[kind], sites: groups.get(kind)!.sort(byName) }));
}
