import { describe, test, expect } from "vitest";
import { releaseTimeline, soonerOptions, zeroLede } from "../results/zero";
import type { CampgroundResult, NotReleasedRange, SearchParams, SearchResponse } from "../api";

// June 2027: Fridays are the 4th, 11th, 18th and 25th. "Today" is 2026-11-07.
const TODAY = "2026-11-07";
const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
  from_location: "seattle", max_drive: 120,
};
const anyDay: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };

const june: NotReleasedRange = { start: "2027-06-01", end: "2027-06-30", releases_on: "2026-12-01" };
const place = (name: string, extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: name, name, booking_system: "recgov", windows: [], total_available_sites: 0,
    not_released_ranges: [june], ...extra }) as CampgroundResult;
const response = (extra: Partial<SearchResponse> = {}): SearchResponse =>
  ({ campgrounds_checked: 2, campgrounds_with_availability: 0, results: [], warnings: [], ...extra });

describe("releaseTimeline", () => {
  test("when each weekend opens, earliest across places", () => {
    const t = releaseTimeline([place("A"), place("B", {
      not_released_ranges: [{ start: "2027-06-11", end: "2027-06-30", releases_on: "2026-12-10" }],
    })], juneWeekends);
    expect(t.items).toEqual([
      { label: "Jun 4 – 6", opens: "2026-12-04" },
      { label: "Jun 11 – 13", opens: "2026-12-10" },
      { label: "Jun 18 – 20", opens: "2026-12-17" },
      { label: "Jun 25 – 27", opens: "2026-12-24" },
    ]);
    expect(t.more).toBe(0);
  });

  test("full weekends and unknown dates aren't on it", () => {
    const t = releaseTimeline([place("A", {
      not_released_ranges: [{ start: "2027-06-18", end: "2027-06-20", releases_on: "2026-12-18" },
        { start: "2027-06-25", end: "2027-06-27", releases_on: null }],
    })], juneWeekends);
    expect(t.items.map((i) => i.label)).toEqual(["Jun 18 – 20"]);
  });

  test("flexible searches list arrivals, the first few and how many more", () => {
    const t = releaseTimeline([place("A")], anyDay);
    expect(t.items[0]).toEqual({ label: "Arrive Tue Jun 1", opens: "2026-12-01" });
    expect(t.items).toHaveLength(6);
    expect(t.more).toBe(23);
  });
});

describe("soonerOptions", () => {
  test("released dates: the same search moved to before booking closes off", () => {
    const [opt] = soonerOptions(response(), [place("A")], juneWeekends, TODAY);
    // Jun 1 opens in 24 days, so nights ~24 days before it are open now; 3 days' margin.
    expect(opt).toMatchObject({ title: "Search released dates", detail: "Apr 6 – May 5, already open for booking" });
    expect(opt.params).toMatchObject({ ...juneWeekends, start_date: "2027-04-06", end_date: "2027-05-05" });
  });

  test("nearby dates the backend found open, with its counts", () => {
    const opts = soonerOptions(response({ date_suggestions: [
      { start_date: "2027-06-08", end_date: "2027-07-07", campgrounds_with_availability: 4, reason: "1 week later" },
      { start_date: "2027-06-15", end_date: "2027-07-14", campgrounds_with_availability: 0, reason: "2 weeks later" },
    ] }), [place("A", { not_released_ranges: [] })], juneWeekends, TODAY);
    expect(opts.map((o) => [o.title, o.detail])).toEqual([["Jun 8 – Jul 7", "4 campgrounds open · 1 week later"]]);
    expect(opts[0].params).toMatchObject({ from_location: "seattle", start_date: "2027-06-08" });
  });

  test("a search limited to one booking system offers the others, without inventing a count", () => {
    const opts = soonerOptions(response(), [], { ...juneWeekends, source: "recgov" }, TODAY);
    expect(opts.map((o) => [o.title, o.detail])).toEqual([
      ["Include every booking system", "This search only checked Recreation.gov"],
    ]);
    expect(opts[0].params.source).toBeUndefined();
  });

  test("the backend's fixes become options, in the app's own param names", () => {
    const opts = soonerOptions(response({ action_chips: [
      { action: "expand_radius", label: "Expand to 180 min", params: { max_drive_minutes: 180 } },
      { action: "drop_days", label: "Try any day", params: { days_of_week: null } },
      { action: "watch", label: "Set a watch", params: {} },
    ] }), [], juneWeekends, TODAY);
    expect(opts.map((o) => o.title)).toEqual(["Expand to 180 min", "Try any day"]);
    expect(opts[0].params.max_drive).toBe(180);
    expect(opts[1].params.days_of_week).toBeUndefined();
  });
});

describe("zeroLede", () => {
  test("nothing released: not full, just not open yet, naming the booking system", () => {
    expect(zeroLede(response(), [place("A"), place("B")], juneWeekends)).toBe(
      "The 2 Recreation.gov campgrounds checked aren’t full. Their June weekends just haven’t opened for booking.",
    );
  });

  test("all full", () => {
    expect(zeroLede(response(), [place("A", { not_released_ranges: [] })], anyDay))
      .toBe("The 1 campground checked is full on your dates.");
  });

  test("a mix says both", () => {
    expect(zeroLede(response({ campgrounds_checked: 3 }), [place("A"), place("B", { not_released_ranges: [] })],
      juneWeekends)).toBe("1 of the 2 campgrounds with nothing to book hasn’t released these dates yet. The other is full.");
  });

  test("places taking no reservations aren't called full", () => {
    const closed = { not_released_ranges: [], closed_ranges: [{ start: "2027-06-01", end: "2027-06-30" }] };
    expect(zeroLede(response(), [place("A", closed), place("B", closed)], juneWeekends)).toBe(
      "The 2 campgrounds checked aren’t taking reservations online for these dates: they’re closed, or first-come, first-served only.",
    );
    expect(zeroLede(response(), [place("A", closed), place("B"), place("C", { not_released_ranges: [] })], juneWeekends))
      .toBe("Of the 3 campgrounds with nothing to book, 1 hasn’t released these dates yet, 1 is full and 1 isn’t taking reservations online.");
  });

  test("a booking system that couldn't be checked is named, so nothing reads as everything", () => {
    const r = response({ warnings: [{ kind: "waf_blocked", count: 9, source: "wa_state", message: "" }] });
    expect(zeroLede(r, [place("A")], juneWeekends)).toMatch(
      / WA State Parks couldn’t be checked right now, so its parks may still have openings\.$/,
    );
  });
});
