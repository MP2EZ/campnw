import { describe, test, expect } from "vitest";
import { groupByDriveBand } from "../results/bands";
import type { CampgroundResult } from "../api";

const place = (name: string, drive: number | null, boat = false) =>
  ({ facility_id: name, name, estimated_drive_minutes: drive, boat_in: boat }) as CampgroundResult;

const shape = (bands: ReturnType<typeof groupByDriveBand>) =>
  bands.map((b) => [b.title, b.results.map((r) => r.name)]);

describe("groupByDriveBand", () => {
  test("hour bands, nearest first, boat-in last", () => {
    expect(shape(groupByDriveBand([
      place("Dash Point", 48),
      place("Kanaskat", 72),
      place("Lake Easton", 79),
      place("Schafer", 128),
      place("Blake Island", null, true),
    ]))).toEqual([
      ["Under 1 hour", ["Dash Point"]],
      ["1–2 hours", ["Kanaskat", "Lake Easton"]],
      ["2–3 hours", ["Schafer"]],
      ["Boat-in only", ["Blake Island"]],
    ]);
  });

  test("band edges: 60 minutes is 1–2 hours", () => {
    expect(shape(groupByDriveBand([place("A", 59), place("B", 60), place("C", 119), place("D", 120)])))
      .toEqual([["Under 1 hour", ["A"]], ["1–2 hours", ["B", "C"]], ["2–3 hours", ["D"]]]);
  });

  test("streamed results arrive in any order and still come out by drive time", () => {
    expect(shape(groupByDriveBand([
      place("Boat", 30, true), place("Far", 200), place("Near", 20), place("Mid", 90), place("Nearer", 10),
    ]))).toEqual([
      ["Under 1 hour", ["Nearer", "Near"]],
      ["1–2 hours", ["Mid"]],
      ["3–4 hours", ["Far"]],
      ["Boat-in only", ["Boat"]],
    ]);
  });

  test("a boat-in place says how to get there instead of a drive time", () => {
    const [boat] = groupByDriveBand([place("Blake Island", 85, true)]);
    expect(boat).toMatchObject({ key: "boat-in", title: "Boat-in only" });
    expect(boat.note).toMatch(/No road access/);
  });

  test("no drive times (no starting point) is one untitled group", () => {
    const bands = groupByDriveBand([place("A", null), place("B", null)]);
    expect(bands).toHaveLength(1);
    expect(bands[0].title).toBeNull();
  });

  test("some unknown drive times go after the known ones", () => {
    expect(shape(groupByDriveBand([place("A", null), place("B", 30)])))
      .toEqual([["Under 1 hour", ["B"]], ["Drive time not known", ["A"]]]);
  });

  test("nothing to group", () => {
    expect(groupByDriveBand([])).toEqual([]);
  });
});
