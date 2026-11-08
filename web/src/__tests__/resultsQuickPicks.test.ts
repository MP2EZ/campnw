import { describe, test, expect } from "vitest";
import { quickPicks } from "../results/picks";
import type { CampgroundResult, SearchParams, Window } from "../api";

// June 2027: Fridays are the 4th, 11th, 18th and 25th.
const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};
const anyDay: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };

const win = (site: string, start: string, end: string): Window => ({
  campsite_id: site, site_name: site, loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, is_fcfs: false, booking_url: null,
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null,
});
/** Open on the given June Fridays (two-night stays). */
const place = (name: string, drive: number | null, fridays: number[], extra: Partial<CampgroundResult> = {}) =>
  ({
    facility_id: name, name, booking_system: "recgov", estimated_drive_minutes: drive, tags: [],
    total_available_sites: fridays.length,
    windows: fridays.map((d) => win(name, `2027-06-${String(d).padStart(2, "0")}`, `2027-06-${String(d + 1).padStart(2, "0")}`)),
    ...extra,
  }) as CampgroundResult;

const summary = (picks: ReturnType<typeof quickPicks>) => picks.map((p) => [p.kicker, p.result.name, p.detail]);

describe("quickPicks", () => {
  test("closest, most open weekends, and a setting worth naming: three different places", () => {
    const picks = quickPicks([
      place("Dash Point", 48, [4, 11, 18, 25]),
      place("Lake Easton", 79, [4, 11], { tags: ["lakeside", "swimming"] }),
      place("Fort Casey", 116, [18]),
      place("Kanaskat", 72, [4, 11, 18]),
    ], juneWeekends);
    expect(summary(picks)).toEqual([
      ["Closest", "Dash Point", "~48m · open every June weekend"],
      ["Most open weekends", "Kanaskat", "~1h 12m · open 3 of 4 weekends"],
      ["Lake you can swim in", "Lake Easton", "~1h 19m · open 2 of 4 weekends"],
    ]);
  });

  test("ties on open weekends go to the closer place", () => {
    const picks = quickPicks([
      place("A", 30, [4]),
      place("Far", 150, [4, 11]),
      place("Near", 90, [4, 11]),
    ], juneWeekends);
    expect(picks[1].result.name).toBe("Near");
  });

  test("a setting pick prefers the closest place with the tag", () => {
    const picks = quickPicks([
      place("A", 30, [4, 11]),
      place("B", 40, [4, 11, 18]),
      place("River far", 150, [4], { tags: ["riverside"] }),
      place("River near", 60, [4], { tags: ["riverside"] }),
    ], juneWeekends);
    expect(summary(picks)[2]).toEqual(["On a river", "River near", "~1h · open Jun 4 – 6"]);
  });

  test("flexible searches: most open sites, and when stays start", () => {
    const picks = quickPicks([
      place("A", 30, [8], { total_available_sites: 3 }),
      place("B", 50, [4, 11], { total_available_sites: 40 }),
      place("C", 70, [20], { total_available_sites: 9 }),
    ], anyDay);
    expect(summary(picks)).toEqual([
      ["Closest", "A", "~30m · stays from Tue Jun 8"],
      ["Most open sites", "B", "~50m · 40 sites open"],
    ]);
  });

  test("boat-in places and unknown drives can't be closest", () => {
    const picks = quickPicks([
      place("Island", 10, [4], { boat_in: true }),
      place("Unknown", null, [4]),
      place("Road", 80, [4]),
      place("Other", 90, [4, 11]),
    ], juneWeekends);
    expect(picks[0]).toMatchObject({ kicker: "Closest", result: expect.objectContaining({ name: "Road" }) });
  });

  test("with no drive times there's no closest pick", () => {
    const picks = quickPicks([place("A", null, [4]), place("B", null, [4, 11]), place("C", null, [4])],
      juneWeekends);
    expect(picks.map((p) => p.kicker)).toEqual(["Most open weekends"]);
  });

  test("too few places to choose between gives no picks", () => {
    expect(quickPicks([place("A", 30, [4]), place("B", 50, [4, 11])], juneWeekends)).toEqual([]);
  });
});
