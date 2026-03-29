interface WordmarkProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

// campable wordmark — CSS text, single baseline, no SVG pixel offsets
//
// Design rationale:
//   "camp" lowercase, regular weight → verb/noun, the action
//   "able" lowercase, bold weight → capable, available, findable
//
// Weight contrast (400→700) carries the visual separation between the two
// semantic parts without introducing a physical gap. Both parts share the
// same baseline and color, so they read as a single mark rather than two
// floating words. Plus Jakarta Sans gives it a modern, geometric feel.
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
      aria-label="campable"
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        fontSize,
        lineHeight,
        fontFamily: "var(--font-heading)",
        userSelect: "none",
      }}
    >
      <span
        style={{
          fontWeight: 500,
          color: "currentColor",
          letterSpacing: "0.01em",
        }}
      >
        camp
      </span>
      <span
        style={{
          fontWeight: 700,
          color: "currentColor",
          letterSpacing: "0.01em",
        }}
      >
        able
      </span>
    </span>
  );
}
