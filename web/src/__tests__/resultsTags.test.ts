import { describe, expect, test } from "vitest";
import { tagLabels } from "../results/tags";

describe("tagLabels", () => {
  test("slugs read as words", () => {
    expect(tagLabels(["pet-friendly", "pull-through", "shade", "campfire", "old-growth"]))
      .toEqual(["Pets allowed", "Pull-through sites", "Shaded sites", "Campfires", "Old-growth forest"]);
  });

  test("drops what the fit line or the drive line already says", () => {
    expect(tagLabels(["rv-friendly", "tent-only", "walk-in", "boat-in", "lakeside"])).toEqual(["Lakeside"]);
  });

  test("an unknown slug still reads as words", () => {
    expect(tagLabels(["dark-sky"])).toEqual(["Dark sky"]);
  });
});
