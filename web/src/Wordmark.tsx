interface WordmarkProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

// camPNW wordmark — CSS text, single baseline, no SVG pixel offsets
//
// Design rationale:
//   "cam" lowercase, regular weight → verb/noun, subordinate prefix
//   "PNW" uppercase, heavy weight, open tracking → the place, the identity
//
// Weight contrast (400→800) carries the visual separation between the two
// semantic parts without introducing a physical gap. Both parts share the
// same baseline and color, so they read as a single mark rather than two
// floating words. The tracked caps echo NPS/trail-marker engraved lettering.
//
// Size scale: sm=20px (mobile header), md=28px (default), lg=36px (hero)

const sizes = {
  sm: { fontSize: "20px", lineHeight: 1 },
  md: { fontSize: "28px", lineHeight: 1 },
  lg: { fontSize: "36px", lineHeight: 1 },
};

export function Wordmark({ size = "md", className }: WordmarkProps) {
  const { fontSize, lineHeight } = sizes[size];

  return (
    <span
      aria-label="campnw"
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        fontSize,
        lineHeight,
        userSelect: "none",
      }}
    >
      <span
        style={{
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          fontWeight: 400,
          color: "#2d5016",
          letterSpacing: "0.02em",
        }}
      >
        camp
      </span>
      <span
        style={{
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          fontWeight: 800,
          color: "#2d5016",
          letterSpacing: "0.06em",
        }}
      >
        nw
      </span>
    </span>
  );
}
