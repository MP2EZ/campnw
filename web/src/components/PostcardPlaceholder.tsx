interface PostcardPlaceholderProps {
  name: string;
  region: string;
  state: string;
  tags: string[];
  bookingSystem: string;
}

// Per-source default hex values used both for SVG fills (when the
// browser cannot resolve CSS vars inside SVG attrs — rare) and for the
// vitest unit test that asserts the stripe color. The .is-postcard CSS
// rule overrides these via CSS vars that flip in dark mode.
const SOURCE_THEMES: Record<
  string,
  { stripe: string; text: string; grain: string; grainDot: string }
> = {
  recgov: {
    stripe: "#5a8a32",
    text: "#2d5016",
    grain: "#e8f0e0",
    grainDot: "#d4e4c4",
  },
  wa_state: {
    stripe: "#1a8a7a",
    text: "#14584a",
    grain: "#e0f0ec",
    grainDot: "#cce4dc",
  },
  or_state: {
    stripe: "#d4920a",
    text: "#7d5a1a",
    grain: "#fef3e0",
    grainDot: "#f2dfb8",
  },
  id_state: {
    stripe: "#7d3cb5",
    text: "#5b2d7a",
    grain: "#eee5f5",
    grainDot: "#d8c9e5",
  },
};

const FALLBACK_THEME = SOURCE_THEMES.recgov;

// Simple tag → glyph map. Keys must be lowercase. Glyph is rendered as
// inline SVG content centered in a 24×16 box, with a short label below.
const TAG_GLYPHS: Record<string, { glyph: JSX.Element; label: string }> = {
  oceanfront: {
    label: "oceanfront",
    glyph: (
      <path
        d="M-12,2 Q-6,-4 0,2 T12,2"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    ),
  },
  beach: {
    /* Beach: wave + sun (sun glints on water) */
    label: "beach",
    glyph: (
      <>
        <circle cx="-8" cy="-5" r="2.5" fill="currentColor" stroke="none" />
        <path
          d="M-12,3 Q-6,-2 0,3 T12,3"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </>
    ),
  },
  lakeside: {
    /* Lakeside: wave + mountain reflection */
    label: "lakeside",
    glyph: (
      <>
        <polygon
          points="-10,-6 -3,-1 3,-4 10,-6 10,-2 -10,-2"
          fill="currentColor"
          opacity="0.6"
          stroke="none"
        />
        <path
          d="M-12,4 Q-6,0 0,4 T12,4"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </>
    ),
  },
  river: {
    /* River: flowing wave + reeds */
    label: "river",
    glyph: (
      <>
        <line x1="-10" y1="-7" x2="-10" y2="3" strokeWidth="1.2" />
        <line x1="-7" y1="-5" x2="-7" y2="3" strokeWidth="1.2" />
        <line x1="-4" y1="-7" x2="-4" y2="3" strokeWidth="1.2" />
        <path
          d="M-12,5 Q-6,1 0,5 T12,5"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </>
    ),
  },
  forest: {
    label: "forest",
    glyph: (
      <>
        <polygon points="-8,4 0,-10 8,4" />
        <rect x="-1.5" y="4" width="3" height="5" />
      </>
    ),
  },
  "old-growth": {
    label: "old-growth",
    glyph: (
      <>
        <polygon points="-8,4 0,-10 8,4" />
        <rect x="-1.5" y="4" width="3" height="5" />
      </>
    ),
  },
  mountain: {
    label: "mountain",
    glyph: <polygon points="-10,5 -3,-7 3,-2 10,5" fill="currentColor" />,
  },
  family: {
    label: "family",
    glyph: (
      <>
        <polygon
          points="-10,6 0,-10 10,6"
          fill="none"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <line x1="0" y1="-10" x2="0" y2="6" strokeWidth="2" />
      </>
    ),
  },
  "kid-friendly": {
    label: "family",
    glyph: (
      <>
        <polygon
          points="-10,6 0,-10 10,6"
          fill="none"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <line x1="0" y1="-10" x2="0" y2="6" strokeWidth="2" />
      </>
    ),
  },
  "pet-friendly": {
    label: "pets",
    glyph: (
      <>
        <circle cx="-5" cy="-3" r="2.5" />
        <circle cx="5" cy="-3" r="2.5" />
        <circle cx="-3" cy="3" r="3.5" />
        <circle cx="3" cy="3" r="3.5" />
      </>
    ),
  },
  campfire: {
    label: "fire",
    glyph: (
      <path
        d="M0,-10 Q-6,-4 -5,2 Q-2,6 0,4 Q2,6 5,2 Q6,-4 0,-10 Z"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    ),
  },
  "rv-friendly": {
    label: "RV",
    glyph: (
      <>
        <rect
          x="-10"
          y="-5"
          width="20"
          height="8"
          rx="1.5"
          fill="none"
          strokeWidth="2"
        />
        <circle cx="-6" cy="5" r="2" />
        <circle cx="6" cy="5" r="2" />
      </>
    ),
  },
  "pull-through": {
    label: "RV",
    glyph: (
      <>
        <rect
          x="-10"
          y="-5"
          width="20"
          height="8"
          rx="1.5"
          fill="none"
          strokeWidth="2"
        />
        <circle cx="-6" cy="5" r="2" />
        <circle cx="6" cy="5" r="2" />
      </>
    ),
  },
  trails: {
    label: "trails",
    glyph: (
      <path
        d="M-12,4 L-6,-4 L-1,3 L4,-3 L10,4"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
  hiking: {
    label: "trails",
    glyph: (
      <path
        d="M-12,4 L-6,-4 L-1,3 L4,-3 L10,4"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
  swimming: {
    label: "swim",
    glyph: (
      <>
        {/* Swimmer head */}
        <circle cx="-8" cy="-3" r="2.5" />
        {/* Water line */}
        <path
          d="M-12,4 Q-4,0 4,4 T12,4"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </>
    ),
  },
  fishing: {
    label: "fishing",
    glyph: (
      <>
        {/* Fish body */}
        <path d="M-8,0 Q-2,-5 5,0 Q-2,5 -8,0 Z" />
        {/* Tail */}
        <polygon points="5,0 11,-3 11,3" />
      </>
    ),
  },
  "boat-launch": {
    label: "boats",
    glyph: (
      <>
        {/* Hull */}
        <path
          d="M-10,2 L10,2 L7,-2 L-7,-2 Z"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        {/* Mast + sail */}
        <line x1="0" y1="-2" x2="0" y2="-9" strokeWidth="1.5" />
        <polygon points="0,-9 0,-3 5,-3" />
        {/* Water */}
        <path
          d="M-12,5 Q-6,4 0,5 T12,5"
          strokeWidth="1"
          fill="none"
          opacity="0.6"
        />
      </>
    ),
  },
  shade: {
    label: "shade",
    glyph: (
      <>
        {/* Sun */}
        <circle cx="-5" cy="-3" r="3" fill="none" strokeWidth="1.5" />
        {/* Tree casting shade */}
        <polygon points="2,5 7,-5 12,5" />
        <rect x="6.2" y="5" width="1.6" height="3" />
      </>
    ),
  },
};

function pickTagGlyphs(tags: string[]): { glyph: JSX.Element; label: string }[] {
  const seen = new Set<string>();
  const out: { glyph: JSX.Element; label: string }[] = [];
  for (const t of tags) {
    const norm = t.toLowerCase();
    const entry = TAG_GLYPHS[norm];
    if (entry && !seen.has(entry.label)) {
      seen.add(entry.label);
      out.push(entry);
    }
    if (out.length === 3) break;
  }
  // Fallback: if no recognized tags, always show a tent so the postcard
  // never feels empty.
  if (out.length === 0) {
    out.push(TAG_GLYPHS.family);
  }
  return out;
}

export function PostcardPlaceholder({
  name,
  region,
  state,
  tags,
  bookingSystem,
}: PostcardPlaceholderProps) {
  const theme = SOURCE_THEMES[bookingSystem] ?? FALLBACK_THEME;
  const glyphs = pickTagGlyphs(tags);
  // Subtitle: prefer region, fall back to state. Avoid "Region, WA, WA"
  // duplication when the region already contains the state suffix.
  const regionTrim = (region || "").trim();
  const stateTrim = (state || "").trim();
  const regionHasState =
    !!stateTrim &&
    !!regionTrim &&
    regionTrim.toUpperCase().endsWith(`, ${stateTrim.toUpperCase()}`);
  const subtitle = regionTrim
    ? regionHasState
      ? regionTrim
      : stateTrim
        ? `${regionTrim}, ${stateTrim}`
        : regionTrim
    : stateTrim;

  // Spread glyphs across the postcard with even spacing.
  const glyphSpacing = 60;
  const glyphStart = -((glyphs.length - 1) * glyphSpacing) / 2;

  // Single accessible name that carries all visible content. The inner
  // SVG nodes are `aria-hidden` to prevent NVDA+Chrome / VO+Safari from
  // leaking inner <text> into the AT tree on top of the aria-label.
  const featureLabels = glyphs.map((g) => g.label).join(", ");
  const ariaLabel = subtitle
    ? `${name}, ${subtitle}. Illustrated placeholder. Features: ${featureLabels}.`
    : `${name}. Illustrated placeholder. Features: ${featureLabels}.`;

  // Resolve source-themed CSS variables. App.css defines these per
  // `.postcard-{source}` and they flip automatically in dark mode via
  // tokens.css source-color overrides. Hex fallbacks (theme.*) cover
  // any browser that can't resolve var() inside SVG attrs.
  return (
    <div
      className={`hero is-postcard postcard-${bookingSystem}`}
      data-testid="postcard-placeholder"
    >
      <svg
        viewBox="0 0 600 338"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label={ariaLabel}
      >
        <defs>
          <pattern
            id={`postcard-grain-${bookingSystem}`}
            x="0"
            y="0"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
          >
            <rect width="4" height="4" fill={`var(--pc-grain, ${theme.grain})`} />
            <circle
              cx="2"
              cy="2"
              r="0.5"
              fill={`var(--pc-grain-dot, ${theme.grainDot})`}
              opacity="0.6"
            />
          </pattern>
        </defs>
        {/* Everything below is decorative — the aria-label above carries
            the full accessible name. */}
        <g aria-hidden="true">
          <rect
            width="600"
            height="338"
            fill={`url(#postcard-grain-${bookingSystem})`}
          />
          <rect width="600" height="6" fill={theme.stripe} />
          {/* Madrona pin watermark */}
          <g transform="translate(300, 90)">
            <path
              d="M0,-30 C-22,-30 -28,-12 -28,0 C-28,18 0,40 0,40 C0,40 28,18 28,0 C28,-12 22,-30 0,-30 Z"
              fill={`var(--pc-stripe, ${theme.stripe})`}
              opacity="0.18"
            />
            <path
              d="M-2,18 Q-6,8 -3,-2 Q1,-12 -2,-22"
              stroke={`var(--pc-text, ${theme.text})`}
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
            />
            <circle cx="-8" cy="-10" r="6" fill={`var(--pc-text, ${theme.text})`} />
            <circle cx="0" cy="-18" r="7" fill={`var(--pc-text, ${theme.text})`} />
            <circle cx="8" cy="-12" r="5" fill={`var(--pc-text, ${theme.text})`} />
          </g>
          <text
            x="300"
            y="195"
            textAnchor="middle"
            fontFamily="-apple-system, BlinkMacSystemFont, sans-serif"
            fontSize="26"
            fontWeight="600"
            fill={`var(--pc-text, ${theme.text})`}
          >
            {name}
          </text>
          {subtitle && (
            <text
              x="300"
              y="222"
              textAnchor="middle"
              fontFamily="-apple-system, BlinkMacSystemFont, sans-serif"
              fontSize="13"
              fill={`var(--pc-text, ${theme.text})`}
              opacity="0.85"
            >
              {subtitle}
            </text>
          )}
          <g
            transform="translate(300, 268)"
            fill={`var(--pc-text, ${theme.text})`}
            stroke={`var(--pc-text, ${theme.text})`}
          >
            {glyphs.map((g, i) => (
              <g key={i} transform={`translate(${glyphStart + i * glyphSpacing}, 0)`}>
                {g.glyph}
                <text
                  y="22"
                  textAnchor="middle"
                  fontSize="10"
                  fontFamily="sans-serif"
                  opacity="0.85"
                  stroke="none"
                >
                  {g.label}
                </text>
              </g>
            ))}
          </g>
        </g>
      </svg>
    </div>
  );
}
