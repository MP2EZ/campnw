import type { NotReleasedSummary } from "../api";
import { formatDateRange, formatDay } from "./dates";

/**
 * "18 campgrounds haven't released these dates yet. Booking typically opens
 * Dec 4 – 25." — or null when every requested night is released.
 *
 * "Typically": the date comes from the booking system's usual rolling window,
 * and some campgrounds release on their own schedule.
 */
export function notReleasedMessage(
  summary: Partial<NotReleasedSummary>,
): string | null {
  const count = summary.not_released_campgrounds ?? 0;
  if (count === 0) return null;
  const message = count === 1
    ? "1 campground hasn't released these dates yet."
    : `${count} campgrounds haven't released these dates yet.`;
  const first = summary.releases_on_earliest;
  if (!first) return message;
  const last = summary.releases_on_latest ?? first;
  const opens = first === last ? formatDay(first) : formatDateRange(first, last);
  return `${message} Booking typically opens ${opens}.`;
}
