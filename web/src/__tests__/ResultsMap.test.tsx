import { describe, test, expect, vi, beforeAll, afterAll } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import type { CampgroundResult } from "../api";
import ResultsMap from "../results/ResultsMap";
import { createSelectionStore } from "../results/selection";

expect.extend(toHaveNoViolations);

// Leaflet sizes the map from the container; jsdom has no layout.
const size = { clientWidth: 600, clientHeight: 600 };
beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  for (const [k, v] of Object.entries(size)) {
    Object.defineProperty(HTMLElement.prototype, k, { configurable: true, get: () => v });
  }
});
afterAll(() => {
  vi.unstubAllGlobals();
  // The real getters live on Element.prototype.
  for (const k of Object.keys(size)) delete (HTMLElement.prototype as unknown as Record<string, unknown>)[k];
});

const place = (id: string, name: string, lat: number, lon: number, extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: id, name, latitude: lat, longitude: lon, estimated_drive_minutes: 48,
    total_available_sites: 3, booking_system: "wa_state", windows: [], ...extra }) as CampgroundResult;

const places = [
  place("1", "Dash Point State Park", 47.31, -122.41),
  place("2", "Kanaskat-Palmer State Park", 47.32, -121.9, { estimated_drive_minutes: 72 }),
  place("3", "Blake Island State Park", 47.54, -122.49, { boat_in: true }),
  place("4", "Wallace Falls State Park", 47.87, -121.68, { total_available_sites: 0 }),
];

function renderMap(onSelect = vi.fn()) {
  const selection = createSelectionStore();
  const utils = render(<ResultsMap places={places} searchKey={1} selection={selection} onSelect={onSelect} />);
  return { ...utils, selection, onSelect };
}

describe("ResultsMap", () => {
  test("open places are buttons named by place and drive; full ones are scenery", () => {
    renderMap();
    expect(screen.getByRole("button", { name: "Dash Point State Park, ~48m drive" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("button", { name: "Blake Island State Park, boat-in only" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Wallace Falls/ })).toBeNull();
  });

  test("the key names every kind of pin in words", () => {
    const { container } = renderMap();
    expect(container.querySelector(".rv2-map-legend")).toHaveTextContent(
      "KeyUnder 1 h1–2 hBoat-inNothing to book");
  });

  test("Enter on a pin selects its place; a click does too", () => {
    const { onSelect } = renderMap();
    const pin = screen.getByRole("button", { name: /Kanaskat/ });
    fireEvent.keyDown(pin, { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith("2");
    fireEvent.click(screen.getByRole("button", { name: /Dash Point/ }));
    expect(onSelect).toHaveBeenLastCalledWith("1");
  });

  test("selecting a place from the list marks its pin, and releasing clears it", () => {
    const { selection } = renderMap();
    const pin = screen.getByRole("button", { name: /Kanaskat/ });
    act(() => selection.select("2", "list"));
    expect(pin).toHaveClass("is-selected");
    act(() => selection.release("2"));
    expect(pin).not.toHaveClass("is-selected");
  });

  test("has no axe violations", async () => {
    const { container } = renderMap();
    expect(await axe(container)).toHaveNoViolations();
  });
});
