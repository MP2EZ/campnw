import { describe, test, expect } from "vitest";
import { answerSentence, searchedAgo } from "../results/answer";
import type { SearchParams } from "../api";

const juneWeekends: SearchParams = {
  start_date: "2027-06-01",
  end_date: "2027-06-30",
  mode: "find",
  nights: 2,
  days_of_week: "4,5,6",
  from_location: "seattle",
  max_drive: 180,
};

const done = { checked: 50, notReleased: 0, loading: false };

describe("answerSentence", () => {
  test.each<[string, Partial<SearchParams>, number, string]>([
    ["the design's headline", {}, 22,
      "22 campgrounds have a June weekend open within 3 hours of Seattle."],
    ["singular", {}, 1,
      "1 campground has a June weekend open within 3 hours of Seattle."],
    ["one-night weekend stays are nights, not weekends", { nights: 1 }, 3,
      "3 campgrounds have a June weekend night open within 3 hours of Seattle."],
    ["long weekends", { days_of_week: "3,4,5,6", nights: 3 }, 5,
      "5 campgrounds have a June long weekend open within 3 hours of Seattle."],
    ["a partial month names the range", { start_date: "2027-06-05", end_date: "2027-06-20" }, 4,
      "4 campgrounds have a weekend open Jun 5 – 20 within 3 hours of Seattle."],
    ["no day filter names the stay length", { days_of_week: undefined }, 9,
      "9 campgrounds have a 2-night stay open in June within 3 hours of Seattle."],
    ["custom days are named, not dropped", { days_of_week: "3,4" }, 2,
      "2 campgrounds have a 2-night Thu–Fri stay open in June within 3 hours of Seattle."],
    ["exact dates", { mode: "exact", start_date: "2027-06-04", end_date: "2027-06-06", days_of_week: undefined }, 7,
      "7 campgrounds have sites open Jun 4 – 6 within 3 hours of Seattle."],
    ["'an' before a vowel month", { start_date: "2027-04-01", end_date: "2027-04-30" }, 13,
      "13 campgrounds have an April weekend open within 3 hours of Seattle."],
    ["'an' before eight", { days_of_week: undefined, nights: 8 }, 2,
      "2 campgrounds have an 8-night stay open in June within 3 hours of Seattle."],
    ["no drive limit makes no distance claim", { max_drive: undefined }, 22,
      "22 campgrounds have a June weekend open."],
    ["a drive limit with no origin", { from_location: undefined, max_drive: 120 }, 6,
      "6 campgrounds have a June weekend open within 2 hours’ drive."],
    ["half hours", { max_drive: 90 }, 6,
      "6 campgrounds have a June weekend open within 1.5 hours of Seattle."],
    ["under an hour stays in minutes", { max_drive: 45 }, 6,
      "6 campgrounds have a June weekend open within 45 minutes of Seattle."],
    ["day order doesn't matter", { days_of_week: "6,4,5" }, 22,
      "22 campgrounds have a June weekend open within 3 hours of Seattle."],
    ["a custom origin is kept as typed", { from_location: "Tacoma, WA", max_drive: 60 }, 6,
      "6 campgrounds have a June weekend open within 1 hour of Tacoma, WA."],
    ["state scope", { state: "OR", from_location: "portland" }, 8,
      "8 Oregon campgrounds have a June weekend open within 3 hours of Portland."],
    ["source scope wins over state", { state: "WA", source: "wa_state" }, 8,
      "8 WA State Parks campgrounds have a June weekend open within 3 hours of Seattle."],
    ["name scope", { name: "rainier", max_drive: undefined }, 2,
      "2 campgrounds matching “rainier” have a June weekend open."],
  ])("%s", (_label, overrides, open, expected) => {
    expect(answerSentence({ ...done, params: { ...juneWeekends, ...overrides }, open })).toBe(expected);
  });

  test("zero open says how many were checked rather than claiming none exist", () => {
    expect(answerSentence({ ...done, params: juneWeekends, open: 0, checked: 46 })).toBe(
      "None of the 46 campgrounds checked have a June weekend open within 3 hours of Seattle.",
    );
    expect(answerSentence({ ...done, params: juneWeekends, open: 0, checked: 1 })).toBe(
      "The 1 campground checked doesn’t have a June weekend open within 3 hours of Seattle.",
    );
  });

  test("zero open because nothing is released yet says so", () => {
    expect(
      answerSentence({ ...done, params: juneWeekends, open: 0, checked: 46, notReleased: 46 }),
    ).toBe("Nothing to book yet. These dates haven’t been released for booking.");
  });

  test("zero checked means nothing matched", () => {
    expect(answerSentence({ ...done, params: juneWeekends, open: 0, checked: 0 })).toBe(
      "No campgrounds matched this search.",
    );
  });

  test("a search that didn't finish says so instead of claiming nothing matched", () => {
    const p = juneWeekends;
    expect(answerSentence({ params: p, open: 0, checked: 0, notReleased: 0, loading: false, failed: true }))
      .toBe("The search couldn’t finish.");
    expect(answerSentence({ params: p, open: 0, checked: 12, notReleased: 0, loading: false, failed: true }))
      .toBe("The search stopped after checking 12 campgrounds, and none of them have a June weekend open.");
    expect(answerSentence({ params: p, open: 3, checked: 12, notReleased: 0, loading: false, failed: true }))
      .toBe("3 campgrounds have a June weekend open within 3 hours of Seattle, from a search that didn’t finish.");
  });

  test("while loading it describes the search, not a count", () => {
    expect(answerSentence({ ...done, params: juneWeekends, open: 3, loading: true })).toBe(
      "Checking campgrounds for a June weekend open within 3 hours of Seattle…",
    );
  });

  test("an NL query before its dates are parsed claims no dates", () => {
    const nl: SearchParams = { start_date: "", end_date: "", q: "lake camping soon" };
    expect(answerSentence({ ...done, params: nl, open: 0, checked: 0, loading: true })).toBe(
      "Checking campgrounds…",
    );
    expect(answerSentence({ ...done, params: nl, open: 5 })).toBe("5 campgrounds have sites open.");
  });

  test("an NL query reads from its parsed params", () => {
    const parsed: SearchParams = { ...juneWeekends, q: "june weekends near seattle", mode: undefined };
    expect(answerSentence({ ...done, params: parsed, open: 22 })).toBe(
      "22 campgrounds have a June weekend open within 3 hours of Seattle.",
    );
  });
});

describe("searchedAgo", () => {
  const t = Date.parse("2027-01-10T15:42:00");
  test.each<[number, string]>([
    [0, "searched just now"],
    [59_000, "searched just now"],
    [60_000, "searched 1 min ago"],
    [42 * 60_000, "searched 42 min ago"],
  ])("%i ms later", (elapsed, expected) => {
    expect(searchedAgo(t, t + elapsed)).toBe(expected);
  });

  test("after an hour it gives the clock time", () => {
    expect(searchedAgo(t, t + 61 * 60_000)).toMatch(/^searched at 3:42\s?PM$/i);
  });
});
