import type { SearchParams } from "../api";
import { formatDateRange, parseIsoDate } from "../lib/dates";

/**
 * The results page's headline: what the search found, in one sentence built
 * only from the search params and counts. Every clause is something the search
 * actually constrained, so it never claims a distance, date or scope that
 * wasn't searched (no drive limit → no "within"; a capped or partly failed
 * search with no openings → "none of the N checked", not "none exist").
 */
export interface AnswerInput {
  params: SearchParams | null;
  /** Campgrounds shown with availability. */
  open: number;
  checked: number;
  notReleased: number;
  loading: boolean;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STATES: Record<string, string> = {
  WA: "Washington", OR: "Oregon", ID: "Idaho", MT: "Montana", WY: "Wyoming", CA: "California",
};
const SOURCES: Record<string, string> = {
  recgov: "Recreation.gov", wa_state: "WA State Parks", or_state: "Oregon State Parks",
};
// SearchForm's drive-from keys; anything else came from the NL parser or a
// profile and is shown as typed.
const BASES = new Set([
  "seattle", "bellevue", "portland", "spokane", "bellingham", "bend",
  "bozeman", "missoula", "jackson", "sacramento", "reno", "moscow",
]);

/** "June" when the range is exactly one calendar month, else null. */
function wholeMonth(start: string, end: string): string | null {
  const s = parseIsoDate(start);
  const e = parseIsoDate(end);
  const last = new Date(s.getFullYear(), s.getMonth() + 1, 0).getDate();
  if (s.getDate() !== 1 || e.getFullYear() !== s.getFullYear()
    || e.getMonth() !== s.getMonth() || e.getDate() !== last) return null;
  return s.toLocaleDateString("en-US", { month: "long" });
}

function daysLabel(days: number[]): string {
  const contiguous = days.every((d, i) => i === 0 || d === days[i - 1] + 1);
  return contiguous && days.length > 1
    ? `${DAYS[days[0]]}–${DAYS[days[days.length - 1]]}`
    : days.map((d) => DAYS[d]).join("/");
}

/** "a" or "an", by sound: an April, an 8-night, an 11-night. */
const article = (next: string) => (/^(?:[aeiou]|8|1[18](?!\d))/i.test(next) ? `an ${next}` : `a ${next}`);

/** "a June weekend open", "sites open Jun 4 – 6", "a 2-night stay open in June". */
function whatOpen(p: SearchParams | null): string {
  if (!p?.start_date || !p.end_date) return "sites open";
  if (p.mode === "exact") return `sites open ${formatDateRange(p.start_date, p.end_date)}`;

  const month = wholeMonth(p.start_date, p.end_date);
  const range = formatDateRange(p.start_date, p.end_date);
  const nights = p.nights ?? 1;
  const night = nights === 1;
  const days = (p.days_of_week ?? "").split(",").filter(Boolean).map(Number).sort((x, y) => x - y);
  const key = days.join(",");
  const weekendish: Record<string, string> = {
    "4,5,6": night ? "weekend night" : "weekend",
    "3,4,5,6": night ? "long-weekend night" : "long weekend",
  };
  const kind = weekendish[key];
  if (kind) return month ? `${article(`${month} ${kind}`)} open` : `${article(kind)} open ${range}`;

  const label = key === "0,1,2,3,4" ? "weekday " : days.length ? `${daysLabel(days)} ` : "";
  return `${article(`${nights}-night ${label}stay`)} open ${month ? `in ${month}` : range}`;
}

function hoursLabel(minutes: number): string {
  if (minutes < 60 || minutes % 30 !== 0) return `${minutes} minutes`;
  const h = minutes / 60;
  return h === 1 ? "1 hour" : `${h} hours`;
}

function within(p: SearchParams | null): string {
  if (!p?.max_drive) return "";
  const span = hoursLabel(p.max_drive);
  if (!p.from_location) return ` within ${span}${span.endsWith("hour") ? "’s" : "’"} drive`;
  const key = p.from_location.toLowerCase();
  const place = BASES.has(key) ? key[0].toUpperCase() + key.slice(1) : p.from_location;
  return ` within ${span} of ${place}`;
}

function campgrounds(n: number, p: SearchParams | null): string {
  const scope = (p?.source && SOURCES[p.source]) || (p?.state && STATES[p.state]);
  const noun = `${scope ? `${scope} ` : ""}campground${n === 1 ? "" : "s"}`;
  return p?.name ? `${noun} matching “${p.name}”` : noun;
}

export function answerSentence({ params, open, checked, notReleased, loading }: AnswerInput): string {
  const what = whatOpen(params);
  const where = within(params);
  if (loading) {
    return what === "sites open" ? "Checking campgrounds…" : `Checking campgrounds for ${what}${where}…`;
  }
  if (open > 0) {
    return `${open} ${campgrounds(open, params)} ${open === 1 ? "has" : "have"} ${what}${where}.`;
  }
  if (checked === 0) return "No campgrounds matched this search.";
  if (notReleased >= checked) {
    return "Nothing to book yet. These dates haven’t been released for booking.";
  }
  if (checked === 1) return `The 1 ${campgrounds(1, params)} checked doesn’t have ${what}${where}.`;
  return `None of the ${checked} ${campgrounds(checked, params)} checked have ${what}${where}.`;
}

/**
 * When the search ran — not how old the availability is: the backend serves
 * availability from a cache up to 10 minutes old, so "updated" would overclaim.
 */
export function searchedAgo(at: number, now: number): string {
  const minutes = Math.floor((now - at) / 60_000);
  if (minutes < 1) return "searched just now";
  if (minutes < 60) return `searched ${minutes} min ago`;
  const time = new Date(at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `searched at ${time}`;
}
