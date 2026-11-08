import { describe, test, expect } from "vitest";
import { buildWindowChips, chipCountText, CHIP_LIMIT } from "../results/chips";
import type { CampgroundResult, SearchParams, Window } from "../api";

// June 2027: Fridays are the 4th, 11th, 18th and 25th.
const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};

let n = 0;
const win = (site: string, start: string, end: string, extra: Partial<Window> = {}): Window => ({
  campsite_id: site, site_name: site, loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, is_fcfs: false,
  booking_url: `https://book/${site}/${start}/${n++}`,
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null,
  ...extra,
});

const place = (windows: Window[], extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: "1", name: "Dash Point", booking_system: "wa_state", availability_url: "https://park",
    windows, ...extra }) as CampgroundResult;

const labels = (r: ReturnType<typeof buildWindowChips>) => r.shown.map((c) => c.label);

describe("buildWindowChips: weekend searches", () => {
  test("one chip per weekend, counting distinct sites across the weekend's stays", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-05"),
      win("B", "2027-06-05", "2027-06-06"),
      win("C", "2027-06-04", "2027-06-06"),
      win("A", "2027-06-11", "2027-06-12"),
    ]), juneWeekends);
    expect(r.shown).toEqual([
      expect.objectContaining({ start: "2027-06-04", end: "2027-06-06", label: "Fri 4 – Sun 6", open: 3 }),
      expect.objectContaining({ start: "2027-06-11", end: "2027-06-13", label: "Fri 11 – Sun 13", open: 1 }),
    ]);
    expect(r.more).toEqual([]);
  });

  test("a site open on two separate nights of one weekend counts once", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-04", { nights: 1 }),
      win("A", "2027-06-06", "2027-06-06", { nights: 1 }),
    ]), { ...juneWeekends, nights: 1 });
    expect(r.shown).toHaveLength(1);
    expect(r.shown[0].open).toBe(1);
  });

  test("a weekend cut by the search range only spans the searched nights", () => {
    const r = buildWindowChips(place([win("A", "2027-06-05", "2027-06-06")]),
      { ...juneWeekends, start_date: "2027-06-05" });
    expect(r.shown[0]).toMatchObject({ start: "2027-06-05", end: "2027-06-06", label: "Sat 5 – Sun 6" });
  });

  test("searches across months put the month in the label", () => {
    const r = buildWindowChips(place([
      win("A", "2027-07-30", "2027-07-31"),
      win("B", "2027-06-04", "2027-06-05"),
    ]), { ...juneWeekends, end_date: "2027-08-31" });
    expect(labels(r)).toEqual(["Fri Jun 4 – Sun 6", "Fri Jul 30 – Sun Aug 1"]);
  });

  test("long weekends and day sets that wrap the week group the same way", () => {
    const thuSun = buildWindowChips(place([win("A", "2027-06-03", "2027-06-05")]),
      { ...juneWeekends, days_of_week: "3,4,5,6" });
    expect(labels(thuSun)).toEqual(["Thu 3 – Sun 6"]);
    const sunMon = buildWindowChips(place([win("A", "2027-06-06", "2027-06-07")]),
      { ...juneWeekends, days_of_week: "6,0" });
    expect(labels(sunMon)).toEqual(["Sun 6 – Mon 7"]);
  });
});

describe("buildWindowChips: exact dates", () => {
  test("one chip for the searched dates, whatever stays the sites have", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-06"),
      win("B", "2027-06-05", "2027-06-06"),
    ]), { start_date: "2027-06-04", end_date: "2027-06-06", mode: "exact", nights: 2 });
    expect(r.shown).toEqual([
      expect.objectContaining({ start: "2027-06-04", end: "2027-06-06", label: "Fri 4 – Sun 6", open: 2 }),
    ]);
  });
});

describe("buildWindowChips: flexible ranges give stay chips", () => {
  const anyDay: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };

  test("one chip per arrival date, labelled arrival to checkout", () => {
    const r = buildWindowChips(place([win("A", "2027-06-08", "2027-06-09")]), anyDay);
    expect(r.shown).toEqual([
      expect.objectContaining({ start: "2027-06-08", end: "2027-06-09", label: "Tue 8 – Thu 10", open: 1 }),
    ]);
  });

  test("a long run of open nights becomes every stay it can hold, not one chip", () => {
    // Prod (2026-11-07): "Sun Nov 22 – Sat Dec 19 · 1 left" for a 28-night run.
    const r = buildWindowChips(place([win("A", "2027-06-01", "2027-06-04")]), anyDay);
    const all = [...r.shown, ...r.more];
    expect(all.map((c) => [c.start, c.end])).toEqual([
      ["2027-06-01", "2027-06-02"], ["2027-06-02", "2027-06-03"], ["2027-06-03", "2027-06-04"],
    ]);
  });

  test("counts distinct sites that can take each stay", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-01", "2027-06-03"),
      win("B", "2027-06-02", "2027-06-03"),
      win("C", "2027-06-02", "2027-06-02", { nights: 1 }),
    ]), anyDay);
    expect(r.shown.map((c) => [c.start, c.open])).toEqual([["2027-06-01", 1], ["2027-06-02", 2]]);
  });

  test("stays don't overlap in a way that double-labels one arrival", () => {
    // Prod: "Nov 22–24", "Nov 22–25", "Nov 22–30" from sites with different runs.
    const r = buildWindowChips(place([
      win("A", "2027-06-22", "2027-06-23"),
      win("B", "2027-06-22", "2027-06-24"),
      win("C", "2027-06-22", "2027-06-29"),
    ]), anyDay);
    const starts = [...r.shown, ...r.more].map((c) => c.start);
    expect(new Set(starts).size).toBe(starts.length);
    expect(r.shown[0]).toMatchObject({ start: "2027-06-22", end: "2027-06-23", open: 3 });
  });

  test("every day of the week selected is the same as none", () => {
    const r = buildWindowChips(place([win("A", "2027-06-01", "2027-06-02")]),
      { ...anyDay, days_of_week: "0,1,2,3,4,5,6" });
    expect(labels(r)).toEqual(["Tue 1 – Thu 3"]);
  });

  test("shows the earliest few arrivals and holds the rest back", () => {
    const days = ["01", "03", "05", "07", "09", "11", "13"];
    const r = buildWindowChips(place(days.map((d) => win(d, `2027-06-${d}`, `2027-06-${d}`, { nights: 1 }))),
      { ...anyDay, nights: 1 });
    expect(r.shown).toHaveLength(CHIP_LIMIT);
    expect(r.shown[0].start).toBe("2027-06-01");
    expect(r.more.map((c) => c.start)).toEqual(days.slice(CHIP_LIMIT).map((d) => `2027-06-${d}`));
  });

  test("never hides a single chip behind “+1 more”", () => {
    const days = Array.from({ length: CHIP_LIMIT + 1 }, (_, i) => String(1 + 2 * i).padStart(2, "0"));
    const r = buildWindowChips(place(days.map((d) => win(d, `2027-06-${d}`, `2027-06-${d}`, { nights: 1 }))),
      { ...anyDay, nights: 1 });
    expect(r.shown).toHaveLength(CHIP_LIMIT + 1);
    expect(r.more).toEqual([]);
  });

  test("a stay always holds its whole length, so it never needs “N+ nights”", () => {
    const r = buildWindowChips(place([win("A", "2027-06-01", "2027-06-05")]), anyDay);
    expect([...r.shown, ...r.more].every((c) => c.minNights === null)).toBe(true);
  });

  test("without search params, each window is its own stay", () => {
    const r = buildWindowChips(place([win("A", "2027-06-01", "2027-06-03", { nights: 3 })]), null);
    expect(labels(r)).toEqual(["Tue 1 – Fri 4"]);
  });
});

describe("buildWindowChips: partial weekend stays", () => {
  const oneNight = { ...juneWeekends, nights: 1 };

  test("a weekend whose sites only offer part of it says the shortest stay", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-04", { nights: 1 }),
      win("B", "2027-06-05", "2027-06-05", { nights: 1 }),
      win("C", "2027-06-04", "2027-06-06", { nights: 3 }),
    ]), oneNight);
    expect(r.shown[0]).toMatchObject({ open: 3, minNights: 1 });
    expect(chipCountText(r.shown[0])).toBe("3 left · 1+ nights");
  });

  test("counts the longest run a site has in the weekend, not its first window", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-04", { nights: 1 }),
      win("A", "2027-06-05", "2027-06-06"),
    ]), oneNight);
    expect(r.shown[0].minNights).toBeNull();
  });

  test("two-night stays in a three-night weekend say 2+ nights", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-05"),
      win("B", "2027-06-05", "2027-06-06"),
    ]), juneWeekends);
    expect(chipCountText(r.shown[0])).toBe("2 left · 2+ nights");
  });

  test("says nothing extra when every site has the whole weekend", () => {
    const r = buildWindowChips(place([win("A", "2027-06-04", "2027-06-06")]), juneWeekends);
    expect(r.shown[0].minNights).toBeNull();
    expect(chipCountText(r.shown[0])).toBe("1 left");
  });
});

describe("buildWindowChips: every chip", () => {
  test("leaves out first-come, first-served sites, which can't be booked", () => {
    const r = buildWindowChips(place([
      win("A", "2027-06-04", "2027-06-05"),
      win("F", "2027-06-01", "2027-06-30", { is_fcfs: true, nights: 0, booking_url: null }),
    ]), juneWeekends);
    expect(r.shown.map((c) => c.open)).toEqual([1]);
  });

  test("is open, fits everyone until there's a party filter, and is few at 5 or under", () => {
    const five = ["A", "B", "C", "D", "E"].map((s) => win(s, "2027-06-04", "2027-06-05"));
    const six = ["A", "B", "C", "D", "E", "F"].map((s) => win(s, "2027-06-11", "2027-06-12"));
    const [a, b] = buildWindowChips(place([...five, ...six]), juneWeekends).shown;
    expect(a).toMatchObject({ status: "open", open: 5, fit: 5, few: true });
    expect(b).toMatchObject({ status: "open", open: 6, fit: 6, few: false });
  });

  test("hands off to the one site's booking page, else the campground's", () => {
    const one = win("A", "2027-06-04", "2027-06-05");
    const r = buildWindowChips(place([
      one,
      win("B", "2027-06-11", "2027-06-12"), win("C", "2027-06-11", "2027-06-12"),
      win("D", "2027-06-18", "2027-06-19", { booking_url: null }),
    ]), juneWeekends);
    expect(r.shown.map((c) => c.href)).toEqual([one.booking_url, "https://park", "https://park"]);
  });
});

describe("chipCountText", () => {
  test("“left” when few, so the count isn't carried by colour alone", () => {
    expect(chipCountText({ open: 3, few: true, minNights: null })).toBe("3 left");
    expect(chipCountText({ open: 1, few: true, minNights: null })).toBe("1 left");
    expect(chipCountText({ open: 40, few: false, minNights: null })).toBe("40 open");
    expect(chipCountText({ open: 40, few: false, minNights: 2 })).toBe("40 open · 2+ nights");
  });
});
