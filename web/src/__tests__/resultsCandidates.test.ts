import { describe, test, expect } from "vitest";
import { candidateWindows, candidateStatus, unavailability, unavailableText } from "../results/candidates";
import type { CampgroundResult, NotReleasedRange, SearchParams, Window } from "../api";

// June 2027: Fridays are the 4th, 11th, 18th and 25th.
const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};
const anyDay: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-07", mode: "find", nights: 2 };
const exact: SearchParams = { start_date: "2027-06-04", end_date: "2027-06-05", mode: "exact", nights: 2 };

const win = (start: string, end: string, extra: Partial<Window> = {}): Window => ({
  campsite_id: "A", site_name: "A", loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, is_fcfs: false, booking_url: null,
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null,
  ...extra,
});
const range = (start: string, end: string, releases_on: string | null): NotReleasedRange =>
  ({ start, end, releases_on });
const place = (windows: Window[], ranges: NotReleasedRange[] = []) =>
  ({ facility_id: "1", name: "Kachess", windows, not_released_ranges: ranges }) as CampgroundResult;

const spans = (p: SearchParams | null) => candidateWindows(p).map((c) => `${c.start}→${c.end}`);

describe("candidateWindows", () => {
  test("weekend searches: every weekend in the range", () => {
    expect(spans(juneWeekends)).toEqual([
      "2027-06-04→2027-06-06", "2027-06-11→2027-06-13", "2027-06-18→2027-06-20", "2027-06-25→2027-06-27",
    ]);
  });

  test("a weekend cut by the range keeps the part searched, if it can hold the stay", () => {
    expect(spans({ ...juneWeekends, start_date: "2027-06-05", end_date: "2027-06-12" }))
      .toEqual(["2027-06-05→2027-06-06", "2027-06-11→2027-06-12"]);
    // Only Sunday left: too short for 2 nights.
    expect(spans({ ...juneWeekends, start_date: "2027-06-06", end_date: "2027-06-10" })).toEqual([]);
  });

  test("day sets that wrap the week stay one block", () => {
    expect(spans({ ...juneWeekends, days_of_week: "6,0", end_date: "2027-06-08" }))
      .toEqual(["2027-06-06→2027-06-07"]);
  });

  test("exact dates: the one stay searched", () => {
    expect(spans(exact)).toEqual(["2027-06-04→2027-06-05"]);
  });

  test("flexible ranges: every arrival with room for the stay", () => {
    const c = candidateWindows(anyDay);
    expect(c.map((x) => x.start)).toEqual(["2027-06-01", "2027-06-02", "2027-06-03", "2027-06-04",
      "2027-06-05", "2027-06-06"]);
    expect(c[0]).toMatchObject({ end: "2027-06-02", stay: true });
  });

  test("no search, no candidates", () => {
    expect(candidateWindows(null)).toEqual([]);
  });
});

describe("candidateStatus", () => {
  const [w1, w2] = candidateWindows(juneWeekends);

  test("open when a bookable window falls in it", () => {
    expect(candidateStatus(place([win("2027-06-05", "2027-06-06")]), w1))
      .toEqual({ status: "open" });
  });

  test("first-come sites don't make it open", () => {
    expect(candidateStatus(place([win("2027-06-04", "2027-06-06", { is_fcfs: true })]), w1))
      .toEqual({ status: "full" });
  });

  test("full when nothing is open and every night is released", () => {
    expect(candidateStatus(place([win("2027-06-04", "2027-06-05")]), w2))
      .toEqual({ status: "full" });
  });

  test("not released, opening when its first unreleased night does", () => {
    const r = place([], [range("2027-06-10", "2027-06-30", "2026-12-10")]);
    expect(candidateStatus(r, w2)).toEqual({ status: "not_released", releasesOn: "2026-12-11" });
  });

  test("not released with no known date when the system has no rule", () => {
    const r = place([], [range("2027-06-04", "2027-06-06", null)]);
    expect(candidateStatus(r, w1)).toEqual({ status: "not_released", releasesOn: null });
  });

  test("a stay is open only if one window holds all of it", () => {
    const [d1, d2] = candidateWindows(anyDay);
    const r = place([win("2027-06-02", "2027-06-03")]);
    expect(candidateStatus(r, d1)).toEqual({ status: "full" });
    expect(candidateStatus(r, d2)).toEqual({ status: "open" });
  });
});

describe("unavailability and its wording", () => {
  test("full every weekend", () => {
    const u = unavailability(place([]), juneWeekends);
    expect(u).toMatchObject({ kind: "full", full: 4, notReleased: 0 });
    expect(unavailableText(u, juneWeekends)).toEqual({ status: "Full all 4 weekends", action: "Watch" });
  });

  test("one full weekend is named", () => {
    const p = { ...juneWeekends, end_date: "2027-06-07" };
    expect(unavailableText(unavailability(place([]), p), p).status).toBe("Full Jun 4 – 6");
  });

  test("nothing released: when booking opens, with the month when the search is one month", () => {
    const r = place([], [range("2027-06-01", "2027-06-30", "2026-12-01")]);
    const u = unavailability(r, juneWeekends);
    expect(u).toMatchObject({ kind: "not_released", releasesFrom: "2026-12-04", releasesThrough: "2026-12-25" });
    expect(unavailableText(u, juneWeekends)).toEqual({ status: "June opens Dec 4 – 25", action: "Remind me" });
  });

  test("not released without a known date says so plainly", () => {
    const r = place([], [range("2027-06-01", "2027-06-30", null)]);
    expect(unavailableText(unavailability(r, juneWeekends), juneWeekends).status).toBe("Not released yet");
  });

  test("some weekends full, the rest not released", () => {
    const r = place([], [range("2027-06-18", "2027-06-30", "2026-12-18")]);
    const u = unavailability(r, juneWeekends);
    expect(u).toMatchObject({ kind: "mixed", full: 2, notReleased: 2 });
    expect(unavailableText(u, juneWeekends))
      .toEqual({ status: "2 weekends full · 2 open Dec 18 – 25", action: "Remind me" });
  });

  test("flexible and exact searches speak of dates, not weekends", () => {
    expect(unavailableText(unavailability(place([]), anyDay), anyDay).status).toBe("Full on your dates");
    expect(unavailableText(unavailability(place([]), exact), exact).status).toBe("Full on your dates");
    const r = place([], [range("2027-06-04", "2027-06-07", "2026-12-04")]);
    expect(unavailableText(unavailability(r, anyDay), anyDay).status).toBe("Partly full · rest opens Dec 4 – 6");
  });
});
