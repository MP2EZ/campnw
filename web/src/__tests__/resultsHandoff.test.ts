import { describe, test, expect } from "vitest";
import { BOOKING_SITES, handoffCopy, stayLabel, stayUrl, type HandoffSite } from "../results/handoff";

describe("stayUrl: the booking link for the nights a site has", () => {
  test("Recreation.gov: start and checkout", () => {
    expect(stayUrl("https://www.recreation.gov/camping/campsites/9?startDate=2027-06-17&endDate=2027-06-21&facilityId=1",
      "2027-06-18", "2027-06-19"))
      .toBe("https://www.recreation.gov/camping/campsites/9?startDate=2027-06-18&endDate=2027-06-20&facilityId=1");
  });

  test("ReserveAmerica: arrival and departure", () => {
    expect(stayUrl("https://www.reserveamerica.com/explore/x/OR/1/2/campsite-booking?arrivalDate=2027-06-17&departureDate=2027-06-21",
      "2027-06-18", "2027-06-19")).toContain("arrivalDate=2027-06-18&departureDate=2027-06-20");
  });

  test("GoingToCamp: start, end and nights", () => {
    expect(stayUrl("https://washington.goingtocamp.com/create-booking/results?mapId=-9&startDate=2027-06-17&endDate=2027-06-21&nights=4&isReserving=true",
      "2027-06-18", "2027-06-18")).toBe(
      "https://washington.goingtocamp.com/create-booking/results?mapId=-9&startDate=2027-06-18&endDate=2027-06-19&nights=1&isReserving=true");
  });

  test("leaves params a link doesn't have alone, and passes null through", () => {
    expect(stayUrl("https://www.recreation.gov/camping/campgrounds/1", "2027-06-18", "2027-06-19"))
      .toBe("https://www.recreation.gov/camping/campgrounds/1");
    expect(stayUrl(null, "2027-06-18", "2027-06-19")).toBeNull();
  });
});

describe("stayLabel and hand-off copy", () => {
  test("arrival to checkout with the nights", () => {
    expect(stayLabel("2027-06-18", "2027-06-19")).toBe("Fri Jun 18 → Sun Jun 20 · 2 nights");
    expect(stayLabel("2027-06-30", "2027-06-30")).toBe("Wed Jun 30 → Thu Jul 1 · 1 night");
  });

  const site = (extra: Partial<HandoffSite> = {}): HandoffSite => ({
    name: "9", loop: "Main", start: "2027-06-18", end: "2027-06-19", perSite: true, ...extra,
  });

  test("names the booking site", () => {
    expect(BOOKING_SITES).toEqual({ recgov: "Recreation.gov", wa_state: "WA State Parks", or_state: "ReserveAmerica" });
  });

  test("says what each booking site fills in, and that the site can go", () => {
    expect(handoffCopy("wa_state", site())).toBe(
      "Opens WA State Parks in a new tab at Main with Jun 18–20 filled in. Find site 9 there, then pay. "
      + "You may need a free account, and their fees and cancellation rules apply. "
      + "Someone else can book the site before you finish.");
    expect(handoffCopy("or_state", site())).toMatch(
      /^Opens site 9 on ReserveAmerica in a new tab with arrival on Fri Jun 18 filled in\. Pick Sun Jun 20 as departure, then pay\. /);
    expect(handoffCopy("recgov", site())).toMatch(
      /^Opens site 9 on Recreation\.gov in a new tab\. Enter Jun 18–20 there, then pay\. /);
  });

  test("a campground-level link says to find the site", () => {
    expect(handoffCopy("recgov", site({ perSite: false }))).toMatch(
      /^Opens Recreation\.gov in a new tab\. Find site 9 and enter Jun 18–20 there, then pay\. /);
  });

  test("ranges across months name both", () => {
    expect(handoffCopy("recgov", site({ start: "2027-06-30", end: "2027-07-01" }))).toContain("Jun 30–Jul 2");
  });
});
