/**
 * Campable brand tokens.
 * Source-of-truth color values. Wire into your design system / Tailwind / CSS vars.
 */

export const colors = {
  /** Primary brand color. Use for the mark, primary buttons, links. */
  green: '#2d5016',
  /** Brighter green for dark surfaces (low-contrast green-on-dark would muddy). */
  greenAccent: '#7fb069',
  /** Default light surface. Acts as the seam-carve color in the mark. */
  cream: '#f5f5f0',
  /** Body text & near-black surfaces. */
  nearBlack: '#1a1a1a',
} as const;

export const typography = {
  /** The wordmark and tabular numbers run on the same monospace family. */
  mono:
    "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace",
} as const;

export const cssVariables = {
  '--campable-green': colors.green,
  '--campable-green-accent': colors.greenAccent,
  '--campable-cream': colors.cream,
  '--campable-near-black': colors.nearBlack,
  /**
   * Default surface color the mark's seam carves through. Set this on the
   * wrapping element if your surface is not cream — the mark reads it via
   * `--mark-bg` and avoids a dirty seam.
   */
  '--mark-bg': colors.cream,
} as const;
