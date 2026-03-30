interface WordmarkProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

// campable wordmark — uniform bold, single baseline
// Plus Jakarta Sans 700, clean and modern
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
        fontSize,
        lineHeight,
        fontFamily: "var(--font-heading)",
        fontWeight: "var(--weight-bold)" as unknown as number,
        letterSpacing: "0.01em",
        color: "currentColor",
        userSelect: "none",
      }}
    >
      campable
    </span>
  );
}
