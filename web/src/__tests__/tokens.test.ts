import { describe, test, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * `var(--x, fallback)` degrades silently by design: a typo'd or never-defined
 * token name never errors, it just permanently pins the fallback. That is how
 * `var(--warning-fg, #b54a00)` shipped — the fallback was theme-blind and
 * measured 3.03:1 on the dark card background, and nothing surfaced it.
 */

const ROOT = join(__dirname, "..");
const FILES = ["App.css", "tokens.css", "pages/MapView.css", "results/results.css", "results/ResultsMap.css"];

function read(f: string) {
  return readFileSync(join(ROOT, f), "utf-8");
}

const ALL_CSS = FILES.map(read).join("\n");

// Declarations look like `  --name: value;` (only in a selector body, never
// inside a var() reference).
function declaredTokens(css: string): Set<string> {
  const out = new Set<string>();
  for (const m of css.matchAll(/^\s*(--[a-zA-Z0-9-]+)\s*:/gm)) out.add(m[1]);
  return out;
}

function referencedTokens(css: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const m of css.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)) {
    out.set(m[1], (out.get(m[1]) ?? 0) + 1);
  }
  return out;
}

describe("CSS custom properties", () => {
  test("every var() reference resolves to a declaration", () => {
    const declared = declaredTokens(ALL_CSS);
    const referenced = referencedTokens(ALL_CSS);

    const undefinedTokens = [...referenced.keys()]
      .filter((t) => !declared.has(t))
      // App sets --header-h at runtime (the sticky header's measured height),
      // so it is legitimately absent from the stylesheets.
      .filter((t) => t !== "--header-h");

    expect(undefinedTokens).toEqual([]);
  });

  test("dark theme redefines the theme colours it overrides", () => {
    const css = read("App.css");
    const rootBlock = css.match(/:root\s*{([^}]*)}/)?.[1] ?? "";
    const darkBlock =
      css.match(/\[data-theme="dark"\]\s*{([^}]*)}/)?.[1] ?? "";

    expect(rootBlock).not.toBe("");
    expect(darkBlock).not.toBe("");

    // Colours whose light value would be unreadable on a dark surface must
    // have a dark counterpart. --text-light was the one that shipped wrong in
    // the other direction (fine in dark, failing AA in light).
    for (const token of ["--bg", "--bg-card", "--text", "--text-muted", "--text-light", "--warning-text"]) {
      expect(darkBlock, `${token} has no dark-mode value`).toContain(token);
    }
  });
});

describe("results v2 token contrast", () => {
  const block = (css: string, selector: RegExp) => {
    const body = css.match(selector)?.[1] ?? "";
    return Object.fromEntries(
      [...body.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]),
    );
  };
  const ROOT_RE = /:root\s*{([^}]*)}/;
  const DARK_RE = /\[data-theme="dark"\]\s*{([^}]*)}/;
  const themes = {
    light: { ...block(read("App.css"), ROOT_RE), ...block(read("tokens.css"), ROOT_RE) },
    dark: { ...block(read("App.css"), DARK_RE), ...block(read("tokens.css"), DARK_RE) },
  };

  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  // [foreground, background, minimum]. 4.5:1 for text, 3:1 for non-text.
  // --chip-full-border is left out on purpose: the dashed edge is decorative
  // and the chip's "Full" label carries the state.
  const PAIRS: [string, string, number][] = [
    ["--chip-open-text", "--chip-open-bg", 4.5],
    ["--chip-full-text", "--chip-full-bg", 4.5],
    ["--notice-info-text", "--notice-info-bg", 4.5],
    ["--chip-few-dot", "--chip-open-bg", 3],
    ["--focus-ring", "--surface-card", 3],
    ["--focus-ring", "--bg", 3],
    ["--focus-ring", "--notice-info-bg", 3],
    ["--pick-kicker", "--surface-tile", 4.5],
    ["--text", "--surface-tile", 4.5],
    // Map pins (D13): each pin's edge against its own halo, so it reads on any tile.
    ["--pin-open", "--pin-halo", 3],
    ["--pin-boat", "--pin-halo", 3],
    ["--pin-muted", "--pin-muted-fill", 3],
    ["--pin-selected", "--pin-halo", 3],
    // --text-muted on --surface-tile is 4.68:1 light (#666 is 3-digit, which
    // this parser skips) and 5.13:1 dark.
  ];

  for (const [theme, tokens] of Object.entries(themes)) {
    test.each(PAIRS)(`${theme}: %s on %s ≥ %d:1`, (fg, bg, min) => {
      expect(tokens[fg], `${fg} missing in ${theme}`).toBeDefined();
      expect(tokens[bg], `${bg} missing in ${theme}`).toBeDefined();
      expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min);
    });
  }
});
