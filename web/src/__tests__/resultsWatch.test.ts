import { describe, test, expect } from "vitest";
import type { CampgroundResult, SearchParams } from "../api";
import { hasFilters, watchRequest, watchStays, whoFromParams, whoText } from "../results/watch";

const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
  people: 4, equipment: "trailer", rig_length: 30,
};

const window = (start: string, end: string) => ({
  campsite_id: "1", start_date: start, end_date: end, is_fcfs: false,
}) as CampgroundResult["windows"][number];

const place = (extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: "232465", name: "Kachess", booking_system: "recgov", windows: [],
    not_released_ranges: [], closed_ranges: [], ...extra }) as CampgroundResult;

describe("watchStays", () => {
  test("weekend searches offer each full weekend, not open or unreleased ones", () => {
    const r = place({
      windows: [window("2027-06-11", "2027-06-12")],
      not_released_ranges: [{ start: "2027-06-25", end: "2027-06-27", releases_on: "2026-12-25" }],
    });
    expect(watchStays(r, juneWeekends)).toEqual([
      { start: "2027-06-04", end: "2027-06-06", label: "Fri Jun 4 – Sun 6" },
      { start: "2027-06-18", end: "2027-06-20", label: "Fri Jun 18 – Sun 20" },
    ]);
  });

  test("exact dates are the one stay", () => {
    const exact = { start_date: "2027-07-02", end_date: "2027-07-03", mode: "exact" };
    expect(watchStays(place(), exact)).toEqual([
      { start: "2027-07-02", end: "2027-07-03", label: "Fri Jul 2 – Sat 3" },
    ]);
  });

  test("flexible ranges watch the whole range", () => {
    const flexible = { start_date: "2027-07-01", end_date: "2027-07-14", mode: "find", nights: 3 };
    expect(watchStays(place(), flexible)).toEqual([
      { start: "2027-07-01", end: "2027-07-14", label: "Thu Jul 1 – Wed 14" },
    ]);
  });

  test("nothing to watch without a search, or when nothing is full", () => {
    expect(watchStays(place(), null)).toEqual([]);
    const allOpen = place({ windows: [window("2027-06-01", "2027-06-30")] });
    expect(watchStays(allOpen, juneWeekends)).toEqual([]);
  });
});

describe("whoFromParams", () => {
  test("takes the search's party and rig", () => {
    expect(whoFromParams(juneWeekends)).toEqual({ people: 4, equipment: "trailer", rigLength: 30 });
  });

  test("ignores a rig length without a trailer and values the API would reject", () => {
    expect(whoFromParams({ people: 2, equipment: "tent", rig_length: 30 }))
      .toEqual({ people: 2, equipment: "tent", rigLength: null });
    expect(whoFromParams({ people: 99, equipment: "boat" }))
      .toEqual({ people: null, equipment: null, rigLength: null });
  });
});

describe("watchRequest", () => {
  const stay = { start: "2027-06-18", end: "2027-06-20", label: "Fri Jun 18 – Sun 20" };

  test("one watch for the stay's nights, with the party, rig and site type", () => {
    const req = watchRequest(place(), stay, juneWeekends, {
      who: whoFromParams(juneWeekends), hookups: true,
    });
    expect(req).toEqual({
      facility_id: "232465", name: "Kachess", start_date: "2027-06-18", end_date: "2027-06-20",
      min_nights: 2, notification_channel: "web_push",
      min_people: 4, equipment: "trailer", rig_length: 30, site_types: ["hookups"],
    });
    expect(hasFilters(req)).toBe(true);
  });

  test("an exact stay needs all its nights; no filters stay unset", () => {
    const exact = { start_date: "2027-07-02", end_date: "2027-07-04", mode: "exact" };
    const req = watchRequest(place(), { start: "2027-07-02", end: "2027-07-04", label: "" }, exact, {
      who: { people: null, equipment: null, rigLength: null }, hookups: false,
    });
    expect(req.min_nights).toBe(3);
    expect(req).not.toHaveProperty("min_people");
    expect(req).not.toHaveProperty("site_types");
    expect(hasFilters(req)).toBe(false);
  });
});

describe("whoText", () => {
  test("says the party and rig the way the search bar does", () => {
    expect(whoText({ people: 4, equipment: "trailer", rigLength: 30 })).toBe("4 people · 30′ trailer");
    expect(whoText({ people: 1, equipment: "tent", rigLength: null })).toBe("1 person · Tent");
    expect(whoText({ people: null, equipment: null, rigLength: null })).toBe("Any party size");
  });
});
