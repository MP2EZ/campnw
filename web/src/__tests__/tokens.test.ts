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
const FILES = ["App.css", "tokens.css", "pages/MapView.css"];

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
      // Set at runtime from TSX via inline style (CSS custom property
      // passthrough), so they are legitimately absent from the stylesheets.
      .filter((t) => !t.startsWith("--pc-") && t !== "--week-count");

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
