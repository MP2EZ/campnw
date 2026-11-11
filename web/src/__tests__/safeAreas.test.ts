import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/** The declarations of the first rule whose selector is exactly `selector`. */
function rule(file: string, selector: string): string {
  const css = readFileSync(join(__dirname, "../results", file), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
  for (const [, sel, body] of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (sel.trim() === selector) return body;
  }
  throw new Error(`${selector} not found in ${file}`);
}

// What sits against a screen edge in the v2 results page, and the inset it
// must clear in the Capacitor shell (notch, Dynamic Island, home indicator).
// max() rather than calc(+) where the shell might inset the edge natively
// too (ios.contentInset), so the gap can't double.
const EDGES: Array<[file: string, selector: string, inset: string, prop: RegExp]> = [
  ["mapSheet.css", ".rv2-sheet-launch-wrap", "bottom", /bottom:[^;]*/],
  ["mapSheet.css", ".rv2-sheet", "top", /--sheet-top:[^;]*/],
  ["mapSheet.css", ".rv2-sheet-panel", "bottom", /padding:[^;]*/],
  ["mapSheet.css", ".rv2-sheet-panel", "left", /padding:[^;]*/],
  ["mapSheet.css", ".rv2-sheet-panel", "right", /padding:[^;]*/],
  ["searchBar.css", ".sb-sheet", "top", /max-height:[^;]*/],
  ["searchBar.css", ".sb-sheet", "left", /padding:[^;]*/],
  ["searchBar.css", ".sb-sheet-foot", "bottom", /padding-bottom:[^;]*/],
  ["results.css", ".rv2-map-aside", "top", /--aside-top:[^;]*/],
  ["sitePanel.css", ".rv2-panel", "top", /padding-top:[^;]*/],
  ["sitePanel.css", ".rv2-panel-foot", "bottom", /padding:[^;]*/],
  ["results.css", ".rv2-card", "top", /scroll-margin-top:[^;]*/],
];

describe("safe areas (v1.48 P4a)", () => {
  test.each(EDGES)("%s %s clears the %s inset", (file, selector, inset, prop) => {
    const decl = rule(file, selector).match(prop)?.[0] ?? "";
    expect(decl, `${selector}: ${prop}`).toContain(`env(safe-area-inset-${inset})`);
    // Offsets from an edge the shell may inset natively use max(), not +.
    if (!decl.startsWith("padding")) expect(decl).toMatch(/max\(/);
  });

  test("the search sheet's Search button isn't padded twice for the home indicator", () => {
    expect(rule("searchBar.css", ".sb-sheet")).not.toMatch(/padding:[^;]*inset-bottom/);
  });
});
