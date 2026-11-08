import { describe, test, expect } from "vitest";
import type { CampgroundResult } from "../api";
import { pinLabel, pinLegend, pinStyle, pinSvg, type PinStyle } from "../results/pins";

const place = (drive: number | null, extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: "1", name: "Dash Point", estimated_drive_minutes: drive, total_available_sites: 4,
    ...extra }) as CampgroundResult;

describe("pinStyle", () => {
  test.each([
    [0, "near", "solid"],
    [59, "near", "solid"],
    [60, "mid", "half"],
    [119, "mid", "half"],
    [120, "far", "ring"],
    [400, "far", "ring"],
  ])("an open place %i min away is %s (%s)", (drive, tier, shape) => {
    expect(pinStyle(place(drive))).toEqual({ tier, shape, muted: false });
  });
});

describe("pinStyle: places without a drive band", () => {
  test("no drive time is a small dot, not a guess at a band", () => {
    expect(pinStyle(place(null))).toEqual({ tier: "unknown", shape: "dot", muted: false });
  });

  test("boat-in is a diamond whatever the drive to the shore", () => {
    expect(pinStyle(place(30, { boat_in: true }))).toEqual({ tier: "boat", shape: "diamond", muted: false });
  });
});

describe("pinStyle: nothing to book", () => {
  test("a full or not-released place is a muted ring at any distance", () => {
    for (const drive of [20, 90, 200, null]) {
      expect(pinStyle(place(drive, { total_available_sites: 0 }))).toEqual({ tier: "none", shape: "ring", muted: true });
    }
  });

  test("a boat-in place keeps its diamond when it's full", () => {
    expect(pinStyle(place(30, { boat_in: true, total_available_sites: 0 })))
      .toEqual({ tier: "none", shape: "diamond", muted: true });
  });
});

describe("pinLabel", () => {
  test("names the place and its drive", () => {
    expect(pinLabel(place(48))).toBe("Dash Point, ~48m drive");
  });

  test("boat-in says so instead of the drive to the shore", () => {
    expect(pinLabel(place(85, { boat_in: true }))).toBe("Dash Point, boat-in only");
  });

  test("an unknown drive is left out", () => {
    expect(pinLabel(place(null))).toBe("Dash Point");
  });
});

describe("pinLegend", () => {
  const s = (tier: PinStyle["tier"]): PinStyle => ({ tier, shape: "solid", muted: tier === "none" });

  test("lists only the kinds on the map, in a fixed order", () => {
    expect(pinLegend([s("none"), s("near"), s("boat"), s("near")]).map((e) => e.text))
      .toEqual(["Under 1 h", "Boat-in", "Nothing to book"]);
  });

  test("a full boat-in place adds both the boat-in and the nothing-to-book rows", () => {
    expect(pinLegend([{ tier: "none", shape: "diamond", muted: true }]).map((e) => e.text))
      .toEqual(["Boat-in", "Nothing to book"]);
  });

  test("every kind has words, so the legend never relies on colour", () => {
    const all = pinLegend((["near", "mid", "far", "unknown", "boat", "none"] as const).map(s));
    expect(all.map((e) => e.text)).toEqual(
      ["Under 1 h", "1–2 h", "2 h or more", "Drive not known", "Boat-in", "Nothing to book"]);
    expect(new Set(all.map((e) => e.style.shape + e.style.muted)).size).toBe(all.length);
  });
});

describe("pinSvg", () => {
  const shapes = ["solid", "half", "ring", "dot", "diamond"] as const;

  test("each shape draws differently and is hidden from assistive tech", () => {
    const svgs = shapes.map((shape) => pinSvg({ tier: "near", shape, muted: false }));
    expect(new Set(svgs).size).toBe(shapes.length);
    for (const svg of svgs) expect(svg).toMatch(/^<svg [^>]*aria-hidden="true"/);
  });

  test("muted pins carry the muted class (dashed edge in CSS)", () => {
    expect(pinSvg({ tier: "none", shape: "ring", muted: true })).toContain("rv2-pin--muted");
    expect(pinSvg({ tier: "far", shape: "ring", muted: false })).not.toContain("rv2-pin--muted");
  });
});
