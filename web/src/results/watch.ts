import type { CampgroundResult, CreateWatchParams, SearchParams } from "../api";
import { candidateStatus, candidateWindows, nightsIn, searchedDays } from "./candidates";
import { chipLabel } from "./chips";
import type { Equipment } from "./searchState";

/**
 * Per-weekend watches (v1.48 D8): what the Watch sheet can watch at a place,
 * and the one watch it creates. Dates are nights, like a chip's.
 */
export interface WatchStay {
  start: string;
  end: string;
  label: string;
}

/** The party and rig a watch's sites must fit; null = any. */
export interface WatchWho {
  people: number | null;
  equipment: Equipment | null;
  rigLength: number | null;
}

const EQUIPMENT = new Set<string>(["tent", "van", "trailer"]);
const inRange = (n: number | undefined, max: number) => n != null && n >= 1 && n <= max ? n : null;

/**
 * The full stays: each full weekend (or block of searched days), the exact
 * dates, or for a flexible range the whole range. Open and not-released
 * stays aren't watched: one is bookable, the other needs a release reminder.
 */
export function watchStays(r: CampgroundResult, p: SearchParams | null): WatchStay[] {
  const candidates = candidateWindows(p);
  const full = candidates.filter((c) => candidateStatus(r, c).status === "full");
  if (full.length === 0 || !p?.start_date || !p.end_date) return [];
  const stays = p.mode === "exact" || searchedDays(p) ? full : [{ start: p.start_date, end: p.end_date }];
  return stays.map(({ start, end }) => ({ start, end, label: chipLabel(start, end, true) }));
}

export function whoFromParams(p: SearchParams | null): WatchWho {
  const equipment = p?.equipment && EQUIPMENT.has(p.equipment) ? p.equipment as Equipment : null;
  return {
    people: inRange(p?.people, 50),
    equipment,
    rigLength: equipment === "trailer" ? inRange(p?.rig_length, 100) : null,
  };
}

/** One watch for one stay. Only push reaches people today (web_push needs an account). */
export function watchRequest(
  r: CampgroundResult,
  stay: WatchStay,
  p: SearchParams | null,
  { who, hookups }: { who: WatchWho; hookups: boolean },
): CreateWatchParams {
  const req: CreateWatchParams = {
    facility_id: r.facility_id,
    name: r.name,
    start_date: stay.start,
    end_date: stay.end,
    min_nights: p?.mode === "exact" ? nightsIn(stay.start, stay.end) : (p?.nights || 1),
    notification_channel: "web_push",
  };
  if (who.people) req.min_people = who.people;
  if (who.equipment) req.equipment = who.equipment;
  if (who.equipment === "trailer" && who.rigLength) req.rig_length = who.rigLength;
  if (hookups) req.site_types = ["hookups"];
  return req;
}

export const hasFilters = (req: CreateWatchParams) =>
  !!(req.min_people || req.equipment || req.site_types?.length);

const RIG: Record<Equipment, string> = { tent: "Tent", van: "Van", trailer: "Trailer" };

/** "4 people · 30′ trailer", "Any party size". */
export function whoText({ people, equipment, rigLength }: WatchWho): string {
  const party = people ? `${people} ${people === 1 ? "person" : "people"}` : "Any party size";
  if (!equipment) return party;
  return `${party} · ${equipment === "trailer" && rigLength ? `${rigLength}′ trailer` : RIG[equipment]}`;
}
