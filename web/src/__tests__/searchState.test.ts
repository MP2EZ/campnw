import { describe, expect, test } from "vitest";
import {
  barToParams, compactLabel, DEFAULT_BAR, driveLabel, monthOptions, monthRange,
  nextWeekend, paramsToBar, quickDates, thisWeekend, whenLabel, whereLabel, whoLabel,
  type BarState,
} from "../results/searchState";
import { parseSearchParamsFromUrl } from "../hooks/useSearch";

// Saturday.
const SAT = "2026-11-07";
const bar = (over: Partial<BarState> = {}): BarState => ({ ...DEFAULT_BAR, ...over });

describe("weekends", () => {
  test("this weekend is the Fri–Sun nights around today, from today", () => {
    expect(thisWeekend("2026-11-04")).toEqual({ start: "2026-11-06", end: "2026-11-08" }); // Wed
    expect(thisWeekend("2026-11-06")).toEqual({ start: "2026-11-06", end: "2026-11-08" }); // Fri
    expect(thisWeekend(SAT)).toEqual({ start: "2026-11-07", end: "2026-11-08" });
    expect(thisWeekend("2026-11-08")).toEqual({ start: "2026-11-13", end: "2026-11-15" }); // Sun
  });

  test("next weekend is the one after this weekend", () => {
    expect(nextWeekend("2026-11-04")).toEqual({ start: "2026-11-13", end: "2026-11-15" });
    expect(nextWeekend(SAT)).toEqual({ start: "2026-11-13", end: "2026-11-15" });
    expect(nextWeekend("2026-11-08")).toEqual({ start: "2026-11-20", end: "2026-11-22" });
  });
});

describe("months", () => {
  test("nine month options from the current month (WA books 9 months out)", () => {
    expect(monthOptions(SAT)).toEqual([
      "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07",
    ]);
  });

  test("the searched month is offered even when it's further out", () => {
    expect(monthOptions(SAT, "2027-10").slice(-2)).toEqual(["2027-07", "2027-10"]);
    expect(monthOptions(SAT, "2027-06")).toHaveLength(9);
  });

  test("a month spans its nights, from today in the current month", () => {
    expect(monthRange("2027-06", SAT)).toEqual({ start: "2027-06-01", end: "2027-06-30" });
    expect(monthRange("2027-02", SAT)).toEqual({ start: "2027-02-01", end: "2027-02-28" });
    expect(monthRange("2026-11", SAT)).toEqual({ start: "2026-11-07", end: "2026-11-30" });
  });
});

describe("barToParams", () => {
  test("month weekends", () => {
    expect(barToParams(bar({ when: { kind: "month", month: "2027-06" }, maxDrive: 180 }), SAT)).toEqual({
      start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2,
      days_of_week: "4,5,6", from_location: "seattle", max_drive: 180, people: 2,
    });
  });

  test("this weekend, any days", () => {
    const p = barToParams(bar({ when: { kind: "this-weekend" }, days: "", nights: 1 }), "2026-11-04");
    expect(p).toMatchObject({ start_date: "2026-11-06", end_date: "2026-11-08", nights: 1, mode: "find" });
    expect(p).not.toHaveProperty("days_of_week");
  });

  test("exact dates: checkout end, nights derived, no day filter", () => {
    const p = barToParams(bar({ when: { kind: "exact", start: "2027-07-02", end: "2027-07-05" } }), SAT);
    expect(p).toMatchObject({ start_date: "2027-07-02", end_date: "2027-07-05", mode: "exact", nights: 3 });
    expect(p).not.toHaveProperty("days_of_week");
  });

  test("a campground name ignores the drive cap", () => {
    const p = barToParams(bar({ name: "Ohanapecosh", maxDrive: 120 }), SAT);
    expect(p.name).toBe("Ohanapecosh");
    expect(p).not.toHaveProperty("max_drive");
  });

  test("who: equipment, and rig length only for trailers", () => {
    expect(barToParams(bar({ people: 4, equipment: "trailer", rigLength: 30 }), SAT))
      .toMatchObject({ people: 4, equipment: "trailer", rig_length: 30 });
    expect(barToParams(bar({ equipment: "van", rigLength: 30 }), SAT)).not.toHaveProperty("rig_length");
    expect(barToParams(bar(), SAT)).not.toHaveProperty("equipment");
  });

  test("keeps the filters the bar doesn't edit, drops a plain-language query", () => {
    const keep = { start_date: "x", end_date: "y", q: "lakes", state: "WA", tags: "lakeside",
      source: "recgov", no_groups: true, include_fcfs: true, limit: 40 };
    expect(barToParams(bar(), SAT, keep)).toMatchObject({
      state: "WA", tags: "lakeside", source: "recgov", no_groups: true, include_fcfs: true, limit: 40,
    });
    expect(barToParams(bar(), SAT, keep)).not.toHaveProperty("q");
  });
});

describe("paramsToBar", () => {
  test("no params gives the defaults", () => {
    expect(paramsToBar(null, SAT)).toEqual(DEFAULT_BAR);
  });

  test("recognises weekends and months", () => {
    expect(paramsToBar({ start_date: "2026-11-07", end_date: "2026-11-08" }, SAT).when).toEqual({ kind: "this-weekend" });
    expect(paramsToBar({ start_date: "2026-11-13", end_date: "2026-11-15" }, SAT).when).toEqual({ kind: "next-weekend" });
    expect(paramsToBar({ start_date: "2027-06-01", end_date: "2027-06-30" }, SAT).when).toEqual({ kind: "month", month: "2027-06" });
    expect(paramsToBar({ start_date: "2026-11-07", end_date: "2026-11-30" }, SAT).when).toEqual({ kind: "month", month: "2026-11" });
  });

  test("anything else is a flexible range or exact dates", () => {
    expect(paramsToBar({ start_date: "2027-06-03", end_date: "2027-07-12" }, SAT).when)
      .toEqual({ kind: "range", start: "2027-06-03", end: "2027-07-12" });
    expect(paramsToBar({ start_date: "2027-07-02", end_date: "2027-07-05", mode: "exact" }, SAT).when)
      .toEqual({ kind: "exact", start: "2027-07-02", end: "2027-07-05" });
  });

  test("reads every bar field back", () => {
    expect(paramsToBar({
      start_date: "2027-06-01", end_date: "2027-06-30", nights: 3, days_of_week: "3,4,5,6",
      from_location: "portland", max_drive: 240, name: "Lost Lake", people: 5, equipment: "trailer", rig_length: 25,
    }, SAT)).toEqual({
      from: "portland", name: "Lost Lake", when: { kind: "month", month: "2027-06" }, days: "3,4,5,6",
      nights: 3, people: 5, equipment: "trailer", rigLength: 25, maxDrive: 240,
    });
  });

  test("ignores equipment it doesn't know", () => {
    expect(paramsToBar({ start_date: "2027-06-01", end_date: "2027-06-30", equipment: "yacht" }, SAT).equipment).toBeNull();
  });

  test("round-trips through the URL", () => {
    const states: BarState[] = [
      bar({ when: { kind: "month", month: "2027-06" }, maxDrive: 180 }),
      bar({ when: { kind: "this-weekend" }, days: "", nights: 1, from: "spokane" }),
      bar({ when: { kind: "exact", start: "2027-07-02", end: "2027-07-05" }, people: 4, equipment: "trailer", rigLength: 30 }),
      bar({ name: "Ohanapecosh", equipment: "van" }),
    ];
    for (const s of states) {
      const params = barToParams(s, SAT);
      const url = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]),
      );
      const back = paramsToBar(parseSearchParamsFromUrl(`?${url}`), SAT);
      // A name search drops the drive cap, so it can't come back.
      expect(back).toEqual(s.name ? { ...s, maxDrive: null } : { ...s, nights: params.nights ?? s.nights });
    }
  });
});

describe("labels", () => {
  test("where", () => {
    expect(whereLabel(bar())).toBe("Near Seattle");
    expect(whereLabel(bar({ from: "bend" }))).toBe("Near Bend");
    expect(whereLabel(bar({ name: "Ohanapecosh" }))).toBe("Ohanapecosh");
    expect(whereLabel(bar({ from: "" }))).toBe("Anywhere");
  });

  test("when", () => {
    expect(whenLabel(bar({ when: { kind: "month", month: "2027-06" } }))).toBe("Weekends in June · 2 nights");
    expect(whenLabel(bar({ when: { kind: "month", month: "2027-06" }, days: "3,4,5,6", nights: 3 }))).toBe("Long weekends in June · 3 nights");
    expect(whenLabel(bar({ when: { kind: "month", month: "2027-06" }, days: "", nights: 1 }))).toBe("June · 1 night");
    expect(whenLabel(bar({ when: { kind: "month", month: "2027-06" }, days: "0,1,2,3,4" }))).toBe("Weekdays in June · 2 nights");
    expect(whenLabel(bar({ when: { kind: "this-weekend" } }))).toBe("This weekend · 2 nights");
    expect(whenLabel(bar({ when: { kind: "next-weekend" }, nights: 1 }))).toBe("Next weekend · 1 night");
    expect(whenLabel(bar({ when: { kind: "exact", start: "2027-07-02", end: "2027-07-05" } }))).toBe("Jul 2 – 5 · 3 nights");
    expect(whenLabel(bar({ when: { kind: "range", start: "2027-06-03", end: "2027-07-12" } }))).toBe("Weekends, Jun 3 – Jul 12 · 2 nights");
    expect(whenLabel(bar({ when: { kind: "range", start: "2027-06-03", end: "2027-07-12" }, days: "" }))).toBe("Jun 3 – Jul 12 · 2 nights");
  });

  test("who", () => {
    expect(whoLabel(bar())).toBe("2 people");
    expect(whoLabel(bar({ people: 1, equipment: "tent" }))).toBe("1 person · Tent");
    expect(whoLabel(bar({ people: 4, equipment: "trailer", rigLength: 30 }))).toBe("4 people · 30′ trailer");
    expect(whoLabel(bar({ equipment: "trailer" }))).toBe("2 people · Trailer");
    expect(whoLabel(bar({ equipment: "van" }))).toBe("2 people · Van");
  });

  test("drive", () => {
    expect(driveLabel(bar({ maxDrive: 180 }))).toBe("Up to 3 h");
    expect(driveLabel(bar({ maxDrive: 90 }))).toBe("Up to 1 h 30");
    expect(driveLabel(bar({ maxDrive: 45 }))).toBe("Up to 45 min");
    expect(driveLabel(bar({ maxDrive: null }))).toBe("Any distance");
    expect(driveLabel(bar({ maxDrive: 180, name: "Ohanapecosh" }))).toBe("Any distance");
  });

  test("compact (mobile)", () => {
    expect(compactLabel(bar({ when: { kind: "month", month: "2027-06" }, equipment: "tent", maxDrive: 180 }))).toEqual({
      title: "Weekends in June",
      detail: "Near Seattle · 2 people, tent · up to 3 h",
    });
    expect(compactLabel(bar({ name: "Ohanapecosh", when: { kind: "this-weekend" } }))).toEqual({
      title: "This weekend",
      detail: "Ohanapecosh · 2 people",
    });
  });
});

describe("quickDates", () => {
  const labels = (b: BarState, today = SAT) => quickDates(b, today).map((c) => c.label);

  test("this weekend, next weekend and the current month, with the searched days", () => {
    expect(labels(bar())).toEqual(["This weekend", "Next weekend", "November weekends"]);
    expect(labels(bar({ days: "3,4,5,6" }))).toEqual(["This weekend", "Next weekend", "November long weekends"]);
    expect(labels(bar({ days: "0,1,2,3,4" }))[2]).toBe("November weekdays");
    expect(labels(bar({ days: "" }))[2]).toBe("November");
    expect(labels(bar({ days: "0,2" }))[2]).toBe("November");
  });

  test("the searched month is the month chip, and it's pressed", () => {
    const chips = quickDates(bar({ when: { kind: "month", month: "2027-06" } }), SAT);
    expect(chips.map((c) => [c.label, c.pressed])).toEqual([
      ["This weekend", false], ["Next weekend", false], ["June weekends", true],
    ]);
    expect(chips[2].when).toEqual({ kind: "month", month: "2027-06" });
    expect(chips[2].year).toBe("2027");
    expect(chips[0].year).toBeUndefined();
  });

  test("the chip matching the search is pressed; a range or exact dates press none", () => {
    expect(quickDates(bar({ when: { kind: "next-weekend" } }), SAT).map((c) => c.pressed)).toEqual([false, true, false]);
    expect(quickDates(bar({ when: { kind: "this-weekend" } }), SAT).map((c) => c.pressed)).toEqual([true, false, false]);
    const exact = bar({ when: { kind: "exact", start: "2026-12-02", end: "2026-12-04" } });
    expect(quickDates(exact, SAT).some((c) => c.pressed)).toBe(false);
  });

  test("late in a month the month chip moves on, once the weekends cover what's left", () => {
    // Wed Nov 25: this weekend Nov 27–29, next weekend Dec 4–6, so November adds nothing.
    expect(labels(bar(), "2026-11-25")[2]).toBe("December weekends");
    expect(quickDates(bar(), "2026-11-25")[2].when).toEqual({ kind: "month", month: "2026-12" });
    // Wed Nov 18: next weekend ends Nov 29, November still has the 30th.
    expect(labels(bar(), "2026-11-18")[2]).toBe("November weekends");
  });

  test("each chip searches through barToParams", () => {
    const [weekend, , month] = quickDates(bar(), SAT);
    expect(barToParams({ ...bar(), when: weekend.when }, SAT)).toMatchObject({ start_date: "2026-11-07", end_date: "2026-11-08" });
    expect(barToParams({ ...bar(), when: month.when }, SAT)).toMatchObject({ start_date: "2026-11-07", end_date: "2026-11-30" });
  });
});
