import type { Window } from "../api";

export const NOT_LISTED = "Site types not listed yet";

const sites = (n: number) => `${n} site${n === 1 ? "" : "s"}`;

/**
 * "Tent · Van · RV ≤30′ · Hookups at 4 sites": what the open sites take, from
 * the per-window fit fields (P1a). Only what some site is known to take is
 * listed: `null` is unknown, never "doesn't fit". An RV site with no length
 * stated has no upper limit, so any such site drops the "≤".
 */
export function fitLine(windows: Window[]): string {
  const open = windows.filter((w) => !w.is_fcfs);
  const parts: string[] = [];
  if (open.some((w) => w.fits_tent)) parts.push("Tent");
  if (open.some((w) => w.fits_van)) parts.push("Van");
  const rvs = open.filter((w) => w.fits_rv);
  if (rvs.length) {
    const lengths = rvs.map((w) => w.max_rv_ft);
    parts.push(lengths.includes(null) ? "RV" : `RV ≤${Math.max(...(lengths as number[]))}′`);
  }
  const count = (has: (w: Window) => boolean | null) =>
    new Set(open.filter(has).map((w) => w.campsite_id)).size;
  const hookups = count((w) => w.hookups);
  if (hookups) parts.push(`Hookups at ${sites(hookups)}`);
  const walkIn = count((w) => w.walk_in);
  if (walkIn) parts.push(`${walkIn} walk-in site${walkIn === 1 ? "" : "s"}`);
  return parts.length ? parts.join(" · ") : NOT_LISTED;
}
