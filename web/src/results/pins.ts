import type { CampgroundResult } from "../api";
import { formatDriveTime } from "../lib/dates";

/** Drive bands match DriveBands' hours: under 1 h, 1–2 h, 2 h or more. */
export type PinTier = "near" | "mid" | "far" | "unknown" | "boat" | "none";
export type PinShape = "solid" | "half" | "ring" | "dot" | "diamond";

export interface PinStyle {
  tier: PinTier;
  shape: PinShape;
  /** Nothing to book: drawn grey with a dashed edge. */
  muted: boolean;
}

/**
 * How a place looks on the map (D13). Shape carries the meaning, so the map
 * reads without colour: fuller pins are closer (solid, half, ring), boat-in
 * is a diamond, and places with nothing to book are dashed rings.
 */
export function pinStyle(r: CampgroundResult): PinStyle {
  if (r.total_available_sites <= 0) {
    return { tier: "none", shape: r.boat_in ? "diamond" : "ring", muted: true };
  }
  if (r.boat_in) return { tier: "boat", shape: "diamond", muted: false };
  const m = r.estimated_drive_minutes;
  if (m == null) return { tier: "unknown", shape: "dot", muted: false };
  if (m < 60) return { tier: "near", shape: "solid", muted: false };
  if (m < 120) return { tier: "mid", shape: "half", muted: false };
  return { tier: "far", shape: "ring", muted: false };
}

/** The pin's accessible name: the place, then how far it is. */
export function pinLabel(r: CampgroundResult): string {
  if (r.boat_in) return `${r.name}, boat-in only`;
  const drive = formatDriveTime(r.estimated_drive_minutes);
  return drive ? `${r.name}, ${drive} drive` : r.name;
}

const LEGEND: [PinTier, string, PinShape][] = [
  ["near", "Under 1 h", "solid"],
  ["mid", "1–2 h", "half"],
  ["far", "2 h or more", "ring"],
  ["unknown", "Drive not known", "dot"],
  ["boat", "Boat-in", "diamond"],
  ["none", "Nothing to book", "ring"],
];

export interface LegendEntry {
  text: string;
  style: PinStyle;
}

/** Legend rows for the kinds of pin on the map, in a fixed order. */
export function pinLegend(styles: PinStyle[]): LegendEntry[] {
  const present = new Set(styles.map((s) => s.tier));
  return LEGEND.filter(([tier]) => present.has(tier))
    .map(([tier, text, shape]) => ({ text, style: { tier, shape, muted: tier === "none" } }));
}

// 24×24, centred on (12, 12). A pale halo keeps each pin readable on any tile.
const HALO = '<circle class="rv2-pin-halo" cx="12" cy="12" r="10"/>';
const SHAPES: Record<PinShape, string> = {
  solid: `${HALO}<circle class="rv2-pin-fill" cx="12" cy="12" r="8"/>`,
  half: `${HALO}<circle class="rv2-pin-body" cx="12" cy="12" r="7"/>`
    + '<path class="rv2-pin-fill" d="M5 12 A7 7 0 0 0 19 12 Z"/>',
  ring: `${HALO}<circle class="rv2-pin-body" cx="12" cy="12" r="6.5"/>`,
  dot: '<circle class="rv2-pin-halo" cx="12" cy="12" r="7"/><circle class="rv2-pin-fill" cx="12" cy="12" r="5"/>',
  diamond: '<path class="rv2-pin-halo" d="M12 1 L23 12 L12 23 L1 12 Z"/>'
    + '<path class="rv2-pin-body" d="M12 4 L20 12 L12 20 L4 12 Z"/>',
};

/** Inline SVG for a pin (map marker and legend). Styled by results-map CSS. */
export function pinSvg(s: PinStyle): string {
  const cls = `rv2-pin rv2-pin--${s.shape}${s.muted ? " rv2-pin--muted" : ""}`;
  return `<svg class="${cls}" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">`
    + `${SHAPES[s.shape]}</svg>`;
}
