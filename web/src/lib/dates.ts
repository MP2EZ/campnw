/**
 * Parse a YYYY-MM-DD string at local noon.
 *
 * Noon, not midnight: `new Date("2026-06-05")` is parsed as UTC, so anywhere
 * west of Greenwich it renders as June 4. The noon offset makes the date
 * survive every timezone.
 */
export function parseIsoDate(iso: string): Date {
  return new Date(iso + "T12:00:00");
}

/** YYYY-MM-DD in the device's time zone (not UTC, which flips the day in the evening west of Greenwich). */
export function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Today on this device, YYYY-MM-DD. */
export function todayIso(now = new Date()): string {
  return toIsoDate(now);
}

/** Python weekday of a YYYY-MM-DD, 0 = Monday (what `days_of_week` uses). */
export function weekday(iso: string): number {
  return (parseIsoDate(iso).getDay() + 6) % 7;
}

/** "Jun 5" */
export function formatDay(iso: string): string {
  return parseIsoDate(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/** "Jun 5 – 7" within a month, "Jun 28 – Jul 2" across one. */
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

/** "~2h 30m". The tilde is deliberate: these are estimates. */
export function formatDriveTime(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `~${m}m`;
  if (m === 0) return `~${h}h`;
  return `~${h}h ${m}m`;
}
