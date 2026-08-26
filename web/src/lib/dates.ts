/**
 * Date and duration formatting.
 *
 * These were implemented four times across the app and had already diverged in
 * ways users could see: three range formatters used an en dash and
 * SmartZeroState used a hyphen, and formatDrive rendered "~2h 15m" on the map
 * but "2h 15m" in itineraries. Same data, different chrome, depending on which
 * screen you were looking at.
 */

/**
 * Parse a YYYY-MM-DD string at local noon.
 *
 * Noon, not midnight: `new Date("2026-06-05")` is parsed as UTC, so anywhere
 * west of Greenwich it renders as June 4. The noon offset makes the date
 * survive every timezone. This trick was hand-rolled in three files.
 */
export function parseIsoDate(iso: string): Date {
  return new Date(iso + "T12:00:00");
}

/** "Jun 5" */
export function formatDay(iso: string): string {
  return parseIsoDate(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/**
 * "Jun 5 – 7" within a month, "Jun 28 – Jul 2" across one.
 *
 * The en dash is the majority convention; SmartZeroState's hyphen was the
 * outlier.
 */
export function formatDateRange(startIso: string, endIso: string): string {
  const s = parseIsoDate(startIso);
  const e = parseIsoDate(endIso);
  const sMonth = s.toLocaleDateString("en-US", { month: "short" });
  if (s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear()) {
    return `${sMonth} ${s.getDate()} – ${e.getDate()}`;
  }
  const eMonth = e.toLocaleDateString("en-US", { month: "short" });
  return `${sMonth} ${s.getDate()} – ${eMonth} ${e.getDate()}`;
}

/**
 * "~2h 30m". The tilde is deliberate — these are estimates, and dropping it
 * (as ItineraryCard did) implies a precision the number does not have.
 */
export function formatDriveTime(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `~${m}m`;
  if (m === 0) return `~${h}h`;
  return `~${h}h ${m}m`;
}
