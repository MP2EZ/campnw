import { describe, test, expect, vi } from "vitest";
import { createSelectionStore } from "../results/selection";

describe("selection store", () => {
  test("starts empty and selects a place from the list or the map", () => {
    const s = createSelectionStore();
    expect(s.get()).toEqual({ id: null, from: null });
    s.select("12", "list");
    expect(s.get()).toEqual({ id: "12", from: "list" });
    s.select("7", "map");
    expect(s.get()).toEqual({ id: "7", from: "map" });
  });

  test("tells subscribers about changes, not repeats", () => {
    const s = createSelectionStore();
    const cb = vi.fn();
    const off = s.subscribe(cb);
    s.select("12", "list");
    s.select("12", "list");
    expect(cb).toHaveBeenCalledTimes(1);
    off();
    s.select("7", "list");
    expect(cb).toHaveBeenCalledTimes(1);
  });

  test("leaving a card clears its hover, but not another card's", () => {
    const s = createSelectionStore();
    s.select("12", "list");
    s.release("7");
    expect(s.get().id).toBe("12");
    s.release("12");
    expect(s.get()).toEqual({ id: null, from: null });
  });

  test("leaving a card keeps a selection made on the map", () => {
    const s = createSelectionStore();
    s.select("12", "map");
    s.release("12");
    expect(s.get()).toEqual({ id: "12", from: "map" });
  });
});

describe("selection store: a pin's card", () => {
  test("hovering or focusing the card a pin chose keeps the map selection", () => {
    const s = createSelectionStore();
    s.select("12", "map");
    s.select("12", "list");
    expect(s.get()).toEqual({ id: "12", from: "map" });
  });
});
