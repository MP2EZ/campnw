import { describe, test, expect } from "vitest";
import { fitLine, NOT_LISTED } from "../results/fit";
import type { Window } from "../api";

const unknown = {
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null,
};
const site = (id: string, fit: Partial<Window> = {}): Window => ({
  campsite_id: id, site_name: id, loop: "", campsite_type: "STANDARD",
  start_date: "2027-06-04", end_date: "2027-06-05", nights: 2, max_people: 6, is_fcfs: false,
  booking_url: null, ...unknown, ...fit,
});

describe("fitLine", () => {
  test("lists what the open sites take, in a fixed order", () => {
    expect(fitLine([
      site("1", { fits_tent: true, fits_rv: true, max_rv_ft: 30, hookups: true }),
      site("2", { fits_van: true, fits_rv: true, max_rv_ft: 20, hookups: true }),
      site("3", { fits_tent: true, hookups: false }),
    ])).toBe("Tent · Van · RV ≤30′ · Hookups at 2 sites");
  });

  test("an RV with no length stated means no upper length, so no ≤", () => {
    expect(fitLine([
      site("1", { fits_rv: true, max_rv_ft: 35 }),
      site("2", { fits_rv: true, max_rv_ft: null }),
    ])).toBe("RV");
  });

  test("unknown is never “doesn't fit”: a park with no fit data says so", () => {
    expect(fitLine([site("1"), site("2")])).toBe(NOT_LISTED);
    expect(NOT_LISTED).toBe("Site types not listed yet");
  });

  test("lists only what some site is known to take", () => {
    expect(fitLine([
      site("1", { fits_tent: true, fits_rv: false }),
      site("2", { fits_rv: null }),
    ])).toBe("Tent");
  });

  test("counts sites, not stays, for hookups and walk-ins", () => {
    expect(fitLine([
      site("1", { fits_tent: true, walk_in: true }),
      site("1", { fits_tent: true, walk_in: true, start_date: "2027-06-11" }),
      site("2", { fits_tent: true, walk_in: true, hookups: true }),
    ])).toBe("Tent · Hookups at 1 site · 2 walk-in sites");
  });

  test("ignores first-come, first-served sites, which the chips leave out too", () => {
    expect(fitLine([
      site("1", { fits_tent: true }),
      site("F", { is_fcfs: true, fits_rv: true, max_rv_ft: 40 }),
    ])).toBe("Tent");
  });
});
