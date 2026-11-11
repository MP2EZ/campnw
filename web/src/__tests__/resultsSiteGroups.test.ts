import { describe, test, expect } from "vitest";
import type { CampgroundResult, SearchParams, Window } from "../api";
import { buildWindowChips } from "../results/chips";
import { panelGroups, siteFit } from "../results/siteGroups";

// June 2027: Fridays are the 4th, 11th, 18th and 25th.
const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5",
};
const flexible: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };

const unknown = { fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null };
const win = (site: string, start: string, end: string, extra: Partial<Window> = {}): Window => ({
  campsite_id: site, site_name: site, loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, max_people_known: true, is_fcfs: false,
  booking_url: `https://www.recreation.gov/camping/campsites/${site}?startDate=${start}&endDate=x&facilityId=1`,
  ...unknown, ...extra,
});
const tent = { fits_tent: true, fits_van: true, fits_rv: false, max_rv_ft: null, hookups: false, walk_in: false };
const rv30 = { fits_tent: true, fits_van: true, fits_rv: true, max_rv_ft: 30, hookups: true, walk_in: false };

const place = (windows: Window[], extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: "1", name: "Fort Ebey", booking_system: "recgov",
    availability_url: "https://www.recreation.gov/camping/campgrounds/1/availability?startDate=2027-06-04",
    windows, ...extra }) as CampgroundResult;

const fri18 = { start: "2027-06-18", end: "2027-06-19" };
const names = (groups: ReturnType<typeof panelGroups>) => groups.map((g) => [g.title, g.sites.map((s) => s.name)]);

describe("panelGroups: which sites a chip has", () => {
  test("only the sites open in that weekend, grouped by type", () => {
    const groups = panelGroups(place([
      win("7", "2027-06-18", "2027-06-19", rv30),
      win("9", "2027-06-18", "2027-06-19", tent),
      win("10", "2027-06-11", "2027-06-12", tent),
      win("2", "2027-06-18", "2027-06-19"),
    ]), fri18, juneWeekends);
    expect(names(groups)).toEqual([
      ["Tent and van sites", ["9"]],
      ["RV and trailer sites", ["7"]],
      ["Site types not listed yet", ["2"]],
    ]);
  });

  test("matches the chip's count", () => {
    const r = place([
      win("A", "2027-06-18", "2027-06-19"), win("B", "2027-06-19", "2027-06-19"),
      win("C", "2027-06-11", "2027-06-12"),
    ]);
    const chip = buildWindowChips(r, juneWeekends).shown.find((c) => c.start === "2027-06-18")!;
    const sites = panelGroups(r, chip, juneWeekends).flatMap((g) => g.sites);
    expect(sites).toHaveLength(chip.open);
  });

  test("a site with part of the weekend says which nights and books just those", () => {
    const [site] = panelGroups(place([win("B", "2027-06-19", "2027-06-19")]), fri18, juneWeekends)[0].sites;
    expect(site.part).toEqual({ start: "2027-06-19", end: "2027-06-19" });
    expect(site.href).toContain("startDate=2027-06-19&endDate=2027-06-20");
  });

  test("whole-weekend sites come before part-weekend ones, then site numbers in order", () => {
    const [group] = panelGroups(place([
      win("10", "2027-06-18", "2027-06-19"), win("2", "2027-06-19", "2027-06-19"),
      win("9", "2027-06-18", "2027-06-19"),
    ]), fri18, juneWeekends);
    expect(group.sites.map((s) => s.name)).toEqual(["9", "10", "2"]);
  });

  test("a flexible stay counts only sites that cover the whole stay", () => {
    const groups = panelGroups(place([
      win("A", "2027-06-08", "2027-06-12"), win("B", "2027-06-09", "2027-06-09"),
    ]), { start: "2027-06-09", end: "2027-06-10" }, flexible);
    const [site] = groups.flatMap((g) => g.sites);
    expect(groups.flatMap((g) => g.sites)).toHaveLength(1);
    expect(site.part).toBeNull();
    // The window runs Jun 8–12; the link books just the stay.
    expect(site.href).toContain("startDate=2027-06-09&endDate=2027-06-11");
  });

  test("first-come sites aren't bookable, so they aren't listed", () => {
    expect(panelGroups(place([win("F", "2027-06-18", "2027-06-19", { is_fcfs: true })]), fri18, juneWeekends))
      .toEqual([]);
  });

  test("walk-in, group and cabin sites get their own groups", () => {
    const groups = panelGroups(place([
      win("W1", "2027-06-18", "2027-06-19", { ...tent, walk_in: true }),
      win("G1", "2027-06-18", "2027-06-19", { campsite_type: "GROUP STANDARD NONELECTRIC" }),
      win("Y1", "2027-06-18", "2027-06-19", { campsite_type: "YURT" }),
    ]), fri18, juneWeekends);
    expect(groups.map((g) => g.title)).toEqual(["Walk-in sites", "Group sites", "Cabins and yurts"]);
  });

  test("searching with a trailer puts RV sites first", () => {
    const groups = panelGroups(place([
      win("9", "2027-06-18", "2027-06-19", tent), win("7", "2027-06-18", "2027-06-19", rv30),
    ]), fri18, { ...juneWeekends, equipment: "trailer", rig_length: 25 });
    expect(groups.map((g) => g.title)).toEqual(["RV and trailer sites", "Tent and van sites"]);
  });

  test("loops read as loops, and a loop that's just the campground's name is dropped", () => {
    const sites = panelGroups(place([
      win("A", "2027-06-18", "2027-06-19", { loop: "F" }),
      win("B", "2027-06-18", "2027-06-19", { loop: "Lower Loop A" }),
      win("C", "2027-06-18", "2027-06-19", { loop: "FORT EBEY " }),
    ]), fri18, juneWeekends)[0].sites;
    expect(sites.map((s) => s.loop)).toEqual(["", "Loop F", "Lower Loop A"]);
  });

  test("capacity shows only when the booking system states it", () => {
    const sites = panelGroups(place([
      win("A", "2027-06-18", "2027-06-19", { max_people: 6 }),
      win("B", "2027-06-18", "2027-06-19", { max_people: 8, max_people_known: false }),
    ]), fri18, juneWeekends)[0].sites;
    expect(sites.map((s) => s.people)).toEqual([6, null]);
  });

  test("without its own link a site falls back to the campground's page for the stay", () => {
    const [site] = panelGroups(place([win("A", "2027-06-18", "2027-06-19", { booking_url: null })]),
      fri18, juneWeekends)[0].sites;
    expect(site.perSite).toBe(false);
    expect(site.href).toBe("https://www.recreation.gov/camping/campgrounds/1/availability?startDate=2027-06-18");
  });
});

describe("siteFit: what one site takes", () => {
  test("lists what it's known to take, with the RV length", () => {
    expect(siteFit(win("7", "", "", rv30))).toBe("Tent, van or RV up to 30′");
  });

  test("says only when the other types are known not to fit", () => {
    expect(siteFit(win("9", "", "", { ...unknown, fits_tent: true, fits_van: false, fits_rv: false })))
      .toBe("Tent only");
    expect(siteFit(win("9", "", "", { ...unknown, fits_tent: true }))).toBe("Tent");
  });

  test("an RV with no length listed has no upper limit stated", () => {
    expect(siteFit(win("1", "", "", { ...unknown, fits_rv: true }))).toBe("RV");
  });

  test("unknown is never \"doesn't fit\"", () => {
    expect(siteFit(win("1", "", ""))).toBe("Site types not listed yet");
    expect(siteFit(win("1", "", "", { ...unknown, fits_tent: false, fits_van: false, fits_rv: false })))
      .toBe("Site types not listed yet");
  });
});
