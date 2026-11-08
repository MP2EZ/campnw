import type { CampgroundResult, SearchParams } from "../api";
import { formatDateRange, formatDriveTime, parseIsoDate } from "../lib/dates";
import { candidateStatus, candidateWindows, searchedDays } from "./candidates";

/**
 * Quick picks: three ways into the results, each chosen from the data alone
 * (D6 dropped the AI summary). Closest, most open, and a setting worth
 * naming, each a different place. No urgency wording.
 */
export interface QuickPick {
  kicker: string;
  result: CampgroundResult;
  detail: string;
}

/** Fewer open places than this and there's nothing to choose between. */
export const MIN_PLACES = 3;

const SETTINGS: [tag: string, kicker: string, needs?: string][] = [
  ["lakeside", "Lake you can swim in", "swimming"],
  ["lakeside", "By a lake"],
  ["riverside", "On a river"],
  ["beach", "On the beach"],
  ["old-growth", "Old-growth forest"],
];

const drive = (r: CampgroundResult) => (r.boat_in ? null : r.estimated_drive_minutes);
const byDrive = (a: CampgroundResult, b: CampgroundResult) =>
  (drive(a) ?? Infinity) - (drive(b) ?? Infinity);

/** Open weekends (or blocks of searched days) out of all of them. */
function openBlocks(r: CampgroundResult, p: SearchParams | null): { open: number; of: number; only: string | null } {
  const candidates = candidateWindows(p);
  const open = candidates.filter((c) => candidateStatus(r, c).status === "open");
  return { open: open.length, of: candidates.length, only: open.length === 1 ? formatDateRange(open[0].start, open[0].end) : null };
}

const sitesOpen = (n: number) => `${n} site${n === 1 ? "" : "s"} open`;

function openSummary(r: CampgroundResult, p: SearchParams | null, weekends: boolean): string {
  if (p?.mode === "exact") return sitesOpen(r.total_available_sites);
  if (!weekends) {
    const first = r.windows.filter((w) => !w.is_fcfs).map((w) => w.start_date).sort()[0];
    if (!first) return "";
    const d = parseIsoDate(first).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    return `stays from ${d.replace(",", "")}`;
  }
  const { open, of, only } = openBlocks(r, p);
  if (open === of && of > 1) {
    const month = p?.start_date && p.start_date.slice(0, 7) === p.end_date.slice(0, 7)
      ? `${parseIsoDate(p.start_date).toLocaleDateString("en-US", { month: "long" })} `
      : "";
    return `open every ${month}weekend`;
  }
  return only ? `open ${only}` : `open ${open} of ${of} weekends`;
}

export function quickPicks(results: CampgroundResult[], p: SearchParams | null): QuickPick[] {
  if (results.length < MIN_PLACES) return [];
  const weekends = !!searchedDays(p) && p?.mode !== "exact";
  const picked = new Set<string>();
  const picks: QuickPick[] = [];
  const add = (kicker: string, r: CampgroundResult | undefined, what?: (r: CampgroundResult) => string) => {
    if (!r || picked.has(r.facility_id)) return;
    picked.add(r.facility_id);
    const where = r.boat_in ? "Boat-in" : formatDriveTime(r.estimated_drive_minutes);
    const open = what ? what(r) : openSummary(r, p, weekends);
    picks.push({ kicker, result: r, detail: [where, open].filter(Boolean).join(" · ") });
  };

  const sorted = [...results].sort(byDrive);
  add("Closest", sorted.find((r) => drive(r) != null));

  const rest = sorted.filter((r) => !picked.has(r.facility_id));
  if (weekends) {
    const score = new Map(rest.map((r) => [r.facility_id, openBlocks(r, p).open]));
    // Stable sort keeps the closer place first on a tie.
    add("Most open weekends", [...rest].sort((a, b) => score.get(b.facility_id)! - score.get(a.facility_id)!)[0]);
  } else {
    add("Most open sites", [...rest].sort((a, b) => b.total_available_sites - a.total_available_sites)[0],
      (r) => sitesOpen(r.total_available_sites));
  }

  for (const [tag, kicker, needs] of SETTINGS) {
    const match = sorted.find((r) => !picked.has(r.facility_id)
      && r.tags?.includes(tag) && (!needs || r.tags.includes(needs)));
    if (match) {
      add(kicker, match);
      break;
    }
  }
  return picks;
}
