import type { CampgroundResult } from "../api";
import { formatDriveTime } from "./dates";
import { sourceLabel } from "./sources";

/** For text interpolated into HTML that Leaflet sets as innerHTML. Names
 * come from third-party data (RIDB, GoingToCamp, ReserveAmerica). */
export const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function httpsUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    return new URL(raw).protocol === "https:" ? raw : null;
  } catch {
    return null;
  }
}

export function mapPopupHtml(r: CampgroundResult): string {
  const label = escapeHtml(sourceLabel(r.booking_system));
  const sourceClass = `source-${escapeHtml(r.booking_system)}`;
  const drive = r.estimated_drive_minutes ? ` · ${formatDriveTime(r.estimated_drive_minutes)} drive` : "";
  const href = httpsUrl(r.availability_url);
  const link = href
    ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">View availability ↗</a>`
    : "";
  return `
    <div class="map-popup">
      <strong>${escapeHtml(r.name)}</strong>
      <span class="source-badge ${sourceClass}">${label}</span>
      <p>${r.total_available_sites} sites available${escapeHtml(drive)}</p>
      ${link}
    </div>
  `;
}
