/**
 * Campable horizontal lockup. Mark + lowercase mono wordmark.
 * Mark always to the left. Three tones for common surfaces.
 */
import * as React from 'react';
import { Mark, CAMPABLE_GREEN, CAMPABLE_GREEN_ACCENT, CAMPABLE_CREAM } from './Mark';

type Tone = 'on-cream' | 'on-dark' | 'on-green';

type LockupProps = {
  /** Pixel height of the mark. Wordmark scales relative to this. */
  size?: number;
  /** Surface the lockup will sit on. Default: 'on-cream'. */
  tone?: Tone;
  className?: string;
  style?: React.CSSProperties;
};

const MONO =
  "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace";

function toneColors(tone: Tone): { fg: string; bg: string } {
  switch (tone) {
    case 'on-dark':
      return { fg: CAMPABLE_GREEN_ACCENT, bg: '#0f0f0e' };
    case 'on-green':
      return { fg: CAMPABLE_CREAM, bg: CAMPABLE_GREEN };
    case 'on-cream':
    default:
      return { fg: CAMPABLE_GREEN, bg: CAMPABLE_CREAM };
  }
}

export function Lockup({
  size = 32,
  tone = 'on-cream',
  className,
  style,
}: LockupProps) {
  const { fg, bg } = toneColors(tone);
  const wordSize = Math.round(size * 0.85);
  const gap = Math.max(6, Math.round(size * 0.32));

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap,
        color: fg,
        ...style,
      }}
      // Surface color is forwarded so the seam carves cleanly. Callers can
      // override by setting `--mark-bg` on a wrapping element.
      data-tone={tone}
    >
      <Mark size={size} bg={bg} title={null} />
      <span
        style={{
          fontFamily: MONO,
          fontSize: wordSize,
          fontWeight: 600,
          letterSpacing: '-0.025em',
          lineHeight: 1,
        }}
      >
        campable
      </span>
    </span>
  );
}

export default Lockup;
