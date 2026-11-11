import { parseIsoDate } from "../lib/dates";
import { addDays, nightsIn } from "./candidates";

/**
 * Hand-off to the booking site (v1.48 P3b): the link for the nights a site
 * has, and what happens after "Book on …". Dates are nights; links get the
 * checkout day after the last night.
 */
export interface HandoffSite {
  name: string;
  /** "Lower Loop A"; empty when unknown. */
  loop: string;
  /** First and last night. */
  start: string;
  end: string;
  /** The link opens this site (or its loop); false: the campground's page. */
  perSite: boolean;
}

/** Where the hand-off lands: Oregon State Parks book on ReserveAmerica. */
export const BOOKING_SITES: Record<string, string> = {
  recgov: "Recreation.gov",
  wa_state: "WA State Parks",
  or_state: "ReserveAmerica",
};

/**
 * The booking link for the nights a site has: rewrites the dates a link
 * already carries (Recreation.gov startDate/endDate, ReserveAmerica
 * arrivalDate/departureDate, GoingToCamp startDate/endDate/nights). The end
 * is the checkout day.
 */
export function stayUrl(url: string | null, start: string, lastNight: string): string | null {
  if (!url) return null;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return url;
  }
  const checkout = addDays(lastNight, 1);
  const values: Record<string, string> = {
    startDate: start, arrivalDate: start, endDate: checkout, departureDate: checkout,
    nights: String(nightsIn(start, lastNight)),
  };
  for (const [key, value] of Object.entries(values)) {
    if (u.searchParams.has(key)) u.searchParams.set(key, value);
  }
  return u.toString();
}

const dayName = (iso: string) => parseIsoDate(iso)
  .toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }).replace(",", "");

/** "Fri Jun 18 → Sun Jun 20 · 2 nights": arrival to checkout. */
export function stayLabel(start: string, lastNight: string): string {
  const n = nightsIn(start, lastNight);
  return `${dayName(start)} → ${dayName(addDays(lastNight, 1))} · ${n} night${n === 1 ? "" : "s"}`;
}

/** "Jun 18–20", "Jun 30–Jul 2": arrival to checkout, compact. */
function rangeText(start: string, lastNight: string): string {
  const s = parseIsoDate(start);
  const e = parseIsoDate(addDays(lastNight, 1));
  const month = (d: Date) => d.toLocaleDateString("en-US", { month: "short" });
  return s.getMonth() === e.getMonth()
    ? `${month(s)} ${s.getDate()}–${e.getDate()}`
    : `${month(s)} ${s.getDate()}–${month(e)} ${e.getDate()}`;
}

const TAIL = "You may need a free account, and their fees and cancellation rules apply. "
  + "Someone else can book the site before you finish.";

/**
 * What happens after "Book on …", true to each booking site (checked
 * 2026-11-11): GoingToCamp fills in both dates at the loop, ReserveAmerica
 * only the arrival, Recreation.gov neither.
 */
export function handoffCopy(system: string, site: HandoffSite): string {
  const where = BOOKING_SITES[system] ?? system;
  const range = rangeText(site.start, site.end);
  let lead: string;
  if (!site.perSite) {
    lead = `Opens ${where} in a new tab. Find site ${site.name} and enter ${range} there, then pay.`;
  } else if (system === "wa_state") {
    lead = `Opens ${where} in a new tab${site.loop ? ` at ${site.loop}` : ""} with ${range} filled in. `
      + `Find site ${site.name} there, then pay.`;
  } else if (system === "or_state") {
    lead = `Opens site ${site.name} on ${where} in a new tab with arrival on ${dayName(site.start)} filled in. `
      + `Pick ${dayName(addDays(site.end, 1))} as departure, then pay.`;
  } else {
    lead = `Opens site ${site.name} on ${where} in a new tab. Enter ${range} there, then pay.`;
  }
  return `${lead} ${TAIL}`;
}
