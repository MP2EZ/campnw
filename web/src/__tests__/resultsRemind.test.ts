import { describe, test, expect } from "vitest";
import type { CampgroundResult, SearchParams } from "../api";
import { REMIND_LIMIT, remindRequest, remindStays } from "../results/watch";

const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};
const TODAY = "2026-11-11";

const place = (extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: "232465", name: "Kachess", booking_system: "recgov", windows: [],
    not_released_ranges: [], closed_ranges: [], ...extra }) as CampgroundResult;

// June nights release 6 months before, one day per night.
const juneNyr = place({
  not_released_ranges: [{ start: "2027-06-18", end: "2027-06-30", releases_on: "2026-12-18" }],
});

describe("remindStays", () => {
  test("each not-released weekend, with the day its first night opens", () => {
    expect(remindStays(juneNyr, juneWeekends, TODAY)).toEqual([
      { start: "2027-06-18", end: "2027-06-20", label: "Fri Jun 18 – Sun 20", releasesOn: "2026-12-18" },
      { start: "2027-06-25", end: "2027-06-27", label: "Fri Jun 25 – Sun 27", releasesOn: "2026-12-25" },
    ]);
  });

  test("a stay whose release date is unknown can't be reminded", () => {
    const unknown = place({ not_released_ranges: [{ start: "2027-06-18", end: "2027-06-30", releases_on: null }] });
    expect(remindStays(unknown, juneWeekends, TODAY)).toEqual([]);
  });

  test("a release date already past is left out", () => {
    expect(remindStays(juneNyr, juneWeekends, "2026-12-20").map((s) => s.releasesOn)).toEqual(["2026-12-25"]);
  });

  test("exact dates are the one stay", () => {
    const exact = { start_date: "2027-06-25", end_date: "2027-06-26", mode: "exact" };
    expect(remindStays(juneNyr, exact, TODAY)).toEqual([
      { start: "2027-06-25", end: "2027-06-26", label: "Fri Jun 25 – Sat 26", releasesOn: "2026-12-25" },
    ]);
  });

  test("flexible searches offer the earliest stays, up to the limit", () => {
    const flexible = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };
    const stays = remindStays(juneNyr, flexible, TODAY);
    expect(stays).toHaveLength(REMIND_LIMIT);
    expect(stays[0]).toEqual(
      { start: "2027-06-17", end: "2027-06-18", label: "Thu Jun 17 – Fri 18", releasesOn: "2026-12-18" },
    );
  });

  test("nothing without a search or with nothing unreleased", () => {
    expect(remindStays(juneNyr, null, TODAY)).toEqual([]);
    expect(remindStays(place(), juneWeekends, TODAY)).toEqual([]);
  });
});

describe("remindRequest", () => {
  test("a release watch for the stay, with its release date and the sheet's filters", () => {
    const stay = remindStays(juneNyr, juneWeekends, TODAY)[0];
    const who = { people: 4, equipment: "trailer" as const, rigLength: 30 };
    expect(remindRequest(juneNyr, stay, juneWeekends, { who, hookups: true })).toEqual({
      facility_id: "232465",
      name: "Kachess",
      start_date: "2027-06-18",
      end_date: "2027-06-20",
      min_nights: 2,
      notification_channel: "web_push",
      watch_type: "release",
      releases_on: "2026-12-18",
      min_people: 4,
      equipment: "trailer",
      rig_length: 30,
      site_types: ["hookups"],
    });
  });
});

describe("createWatch: 422 with a reason", () => {
  test("throws WatchRejectedError carrying the API's code", async () => {
    const { vi } = await import("vitest");
    vi.resetModules();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 422, json: () => Promise.resolve({ detail: { error: "already_released" } }),
    });
    const { createWatch, WatchRejectedError } = await import("../api");
    const err = await createWatch({ start_date: "2027-06-18", end_date: "2027-06-20" }).catch((e) => e);
    expect(err).toBeInstanceOf(WatchRejectedError);
    expect(err.code).toBe("already_released");
  });
});
