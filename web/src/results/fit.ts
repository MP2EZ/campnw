import type { SearchParams, Window } from "../api";

export const NOT_LISTED = "Site types not listed yet";

const sites = (n: number) => `${n} site${n === 1 ? "" : "s"}`;

/** Takes the searched rig, as far as the booking system says. */
function takes(w: Window, { equipment, rig_length }: Pick<SearchParams, "equipment" | "rig_length">): boolean {
  if (equipment === "tent") return !!w.fits_tent;
  if (equipment === "van") return !!w.fits_van;
  if (equipment === "trailer") return !!w.fits_rv && (w.max_rv_ft == null || !rig_length || w.max_rv_ft >= rig_length);
  return false;
}

const RIGS: Record<string, string> = { tent: "tent", van: "van", trailer: "trailer" };

/**
 * "Tent · Van · RV ≤30′ · Hookups at 4 sites": what the open sites take, from
 * the per-window fit fields (P1a). Only what some site is known to take is
 * listed: `null` is unknown, never "doesn't fit". An RV site with no length
 * stated has no upper limit, so any such site drops the "≤".
 *
 * With a rig searched, it leads with how many sites are known to take it
 * instead (UX #18): "12 sites fit your 30′ trailer". Sites known not to take
 * it never reach here (the backend's `who` filter).
 */
export function fitLine(windows: Window[], who?: Pick<SearchParams, "equipment" | "rig_length"> | null): string {
  const open = windows.filter((w) => !w.is_fcfs);
  const parts: string[] = [];
  const count = (has: (w: Window) => boolean | null) =>
    new Set(open.filter(has).map((w) => w.campsite_id)).size;
  const rig = who?.equipment && RIGS[who.equipment];
  const fit = rig ? count((w) => takes(w, who)) : 0;
  if (rig && fit) {
    const length = who.equipment === "trailer" && who.rig_length ? `${who.rig_length}′ ` : "";
    parts.push(`${sites(fit)} fit${fit === 1 ? "s" : ""} your ${length}${rig}`);
  } else {
    if (open.some((w) => w.fits_tent)) parts.push("Tent");
    if (open.some((w) => w.fits_van)) parts.push("Van");
    const rvs = open.filter((w) => w.fits_rv);
    if (rvs.length) {
      const lengths = rvs.map((w) => w.max_rv_ft);
      parts.push(lengths.includes(null) ? "RV" : `RV ≤${Math.max(...(lengths as number[]))}′`);
    }
    // "Hookups at 1 site" alone reads as if hookups were all there is to know.
    if (!parts.length) parts.push(NOT_LISTED);
  }
  const hookups = count((w) => w.hookups);
  if (hookups) parts.push(`Hookups at ${sites(hookups)}`);
  const walkIn = count((w) => w.walk_in);
  if (walkIn) parts.push(`${walkIn} walk-in site${walkIn === 1 ? "" : "s"}`);
  return parts.join(" · ");
}
