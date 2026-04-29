/**
 * Campable mark.
 *
 * Single component with size-aware rendering:
 *   - size <= 18 → pixel-snapped 16px optical variant (1px seam, 1px outline)
 *   - size <= 28 → pixel-snapped 24px optical variant (1.5px outline)
 *   - size  > 28 → vector at the canonical 80px geometry
 *
 * Color is driven by `currentColor` so callers can recolor with `style.color`
 * or a parent `color:` rule. The seam color falls back to the brand cream
 * but should be overridden via the `bg` prop or the `--mark-bg` CSS variable
 * to match the surface the mark sits on (otherwise the seam will look like
 * a notch on a non-cream background).
 */
import * as React from 'react';

export const CAMPABLE_GREEN = '#2d5016';
export const CAMPABLE_GREEN_ACCENT = '#7fb069';
export const CAMPABLE_CREAM = '#f5f5f0';
export const CAMPABLE_NEAR_BLACK = '#1a1a1a';

type MarkProps = {
  /** Pixel size of the rendered square. Default 24. */
  size?: number;
  /**
   * Background color to "carve" the seam through. Default: brand cream.
   * Pass the actual surface color for clean compositing. Or set the
   * `--mark-bg` CSS variable on a wrapping element to control globally.
   */
  bg?: string;
  /** Optional inline color override. Otherwise inherits via currentColor. */
  color?: string;
  className?: string;
  style?: React.CSSProperties;
  /** ARIA label. Pass `null` to render as decorative (aria-hidden). */
  title?: string | null;
};

const SEAM_FALLBACK = 'var(--mark-bg, #f5f5f0)';

export function Mark({
  size = 24,
  bg,
  color,
  className,
  style,
  title = 'Campable',
}: MarkProps) {
  const seam = bg ?? SEAM_FALLBACK;
  const a11y = title === null
    ? { 'aria-hidden': true as const }
    : { role: 'img' as const, 'aria-label': title };
  const commonStyle: React.CSSProperties = {
    color: color ?? 'currentColor',
    display: 'inline-block',
    flexShrink: 0,
    ...style,
  };

  // Hand-tuned 16px: 1px seam slot + 1px outline.
  if (size <= 18) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 16 16"
        shapeRendering="crispEdges"
        className={className}
        style={commonStyle}
        {...a11y}
      >
        <polygon points="10,1 15,1 8,15" fill="currentColor" />
        <polygon points="1,1 15,1 8,15" fill="none" stroke="currentColor" strokeWidth="1" />
        <polygon points="9,1 10,1 8,15" fill={seam} />
      </svg>
    );
  }

  // Hand-tuned 24px: 1px seam slot + 1.5px outline.
  if (size <= 28) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        shapeRendering="crispEdges"
        className={className}
        style={commonStyle}
        {...a11y}
      >
        <polygon points="16,2 22,2 12,22" fill="currentColor" />
        <polygon points="2,2 22,2 12,22" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <polygon points="15,2 16,2 12,22" fill={seam} />
      </svg>
    );
  }

  // Canonical 80px vector. seamT = 0.70.
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      className={className}
      style={commonStyle}
      {...a11y}
    >
      <polygon points="50.4,14 66,14 40,72" fill="currentColor" />
      <polygon
        points="14,14 66,14 40,72"
        fill="none"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <line
        x1="50.4"
        y1="14"
        x2="40"
        y2="72"
        stroke={seam}
        strokeWidth="2.45"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default Mark;
