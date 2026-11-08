import type { CampgroundResult } from "../api";

export interface DriveBand {
  key: string;
  /** "Under 1 hour", "1–2 hours", "Boat-in only"; null when no place has a drive time. */
  title: string | null;
  note?: string;
  results: CampgroundResult[];
}

const BOAT_IN: Omit<DriveBand, "results"> = {
  key: "boat-in",
  title: "Boat-in only",
  note: "No road access. You’ll need a boat or kayak to get there.",
};

/**
 * Places grouped by drive time in whole hours, nearest first, with boat-in
 * places last in their own group (their drive time is to the shore, not the
 * site). Sorted by the backend's own key, (boat_in, drive minutes), because
 * streamed results arrive in the order they were checked.
 */
export function groupByDriveBand(results: CampgroundResult[]): DriveBand[] {
  const order = (r: CampgroundResult) => [r.boat_in ? 1 : 0, r.estimated_drive_minutes ?? Number.MAX_SAFE_INTEGER];
  const sorted = [...results].sort((a, b) => {
    const [ab, ad] = order(a);
    const [bb, bd] = order(b);
    return ab - bb || ad - bd;
  });
  const anyDrive = results.some((r) => !r.boat_in && r.estimated_drive_minutes != null);

  const bands = new Map<string, DriveBand>();
  for (const r of sorted) {
    const minutes = r.estimated_drive_minutes;
    const hours = minutes == null ? null : Math.floor(minutes / 60);
    const band: Omit<DriveBand, "results"> = r.boat_in
      ? BOAT_IN
      : hours == null
        ? { key: "unknown", title: anyDrive ? "Drive time not known" : null }
        : { key: `h${hours}`, title: hours === 0 ? "Under 1 hour" : `${hours}–${hours + 1} hours` };
    if (!bands.has(band.key)) bands.set(band.key, { ...band, results: [] });
    bands.get(band.key)!.results.push(r);
  }
  return [...bands.values()];
}
