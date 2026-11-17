import { describe, expect, test } from "vitest";
import { displayName } from "../lib/displayName";

// Recreation.gov (RIDB) names come in ALL CAPS next to title-case ones.
describe("displayName", () => {
  test.each([
    ["OHANAPECOSH CAMPGROUND", "Ohanapecosh Campground"],
    ["EAST KACHESS GROUP SITE", "East Kachess Group Site"],
    ["DAIRY CREEK WEST", "Dairy Creek West"],
    ["ELEC", "Elec"],
  ])("title-cases an all-caps name: %s", (raw, shown) => {
    expect(displayName(raw)).toBe(shown);
  });

  test("leaves names that already have lower case alone", () => {
    expect(displayName("Fort Ebey State Park")).toBe("Fort Ebey State Park");
    expect(displayName("L.L. Stub Stewart Memorial State Park")).toBe("L.L. Stub Stewart Memorial State Park");
    expect(displayName("Loop DAIRY CREEK")).toBe("Loop DAIRY CREEK");
  });

  test("keeps acronyms and state codes", () => {
    expect(displayName("ELK CREEK CAMPGROUND (SAWTOOTH NF)")).toBe("Elk Creek Campground (Sawtooth NF)");
    expect(displayName("RIVER SIDE (ID - BOISE)")).toBe("River Side (ID - Boise)");
    expect(displayName("FISH CREEK (OR)")).toBe("Fish Creek (OR)");
    expect(displayName("KOA RV PARK")).toBe("KOA RV Park");
  });

  test("keeps Roman numerals and single letters", () => {
    expect(displayName("LOWER LOOP II")).toBe("Lower Loop II");
    expect(displayName("CAMP IV")).toBe("Camp IV");
    expect(displayName("LOOP A")).toBe("Loop A");
    expect(displayName("TILLY JANE A-FRAME")).toBe("Tilly Jane A-Frame");
  });

  test("small words stay lower case except first", () => {
    expect(displayName("LAKE OF THE WOODS")).toBe("Lake of the Woods");
    expect(displayName("THE DALLES")).toBe("The Dalles");
    expect(displayName("KALISPELL ISLAND BOAT-IN CAMPGROUND")).toBe("Kalispell Island Boat-in Campground");
  });

  test("Mc and O' names, possessives and numbers", () => {
    expect(displayName("MCKENZIE BRIDGE")).toBe("McKenzie Bridge");
    expect(displayName("O'NEIL CREEK")).toBe("O'Neil Creek");
    expect(displayName("DEVIL'S LAKE")).toBe("Devil's Lake");
    expect(displayName("034 GROUP")).toBe("034 Group");
    expect(displayName("BIG SPRINGS GRP. AREA")).toBe("Big Springs Grp. Area");
  });

  test("empty and number-only strings pass through", () => {
    expect(displayName("")).toBe("");
    expect(displayName("034")).toBe("034");
  });
});
