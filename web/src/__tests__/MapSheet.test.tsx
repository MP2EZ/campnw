import { describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult } from "../api";
import { MapSheet } from "../results/MapSheet";
import { createSelectionStore } from "../results/selection";

const mapMounts = vi.fn();
// Stands in for the Leaflet map: one pin button per open place.
vi.mock("../results/ResultsMap", () => ({
  default: ({ places, onSelect }: { places: CampgroundResult[]; onSelect: (id: string) => void }) => {
    mapMounts();
    return (
      <div data-testid="results-map">
        {places.map((p) => <button key={p.facility_id} type="button" onClick={() => onSelect(p.facility_id)}>{p.name}</button>)}
      </div>
    );
  },
}));

const place = (id: string, name: string, coords = true) => ({
  facility_id: id, name, total_available_sites: 3,
  latitude: coords ? 47.3 : 0, longitude: coords ? -122.4 : 0,
}) as CampgroundResult;

function setup(places = [place("1", "Dash Point"), place("2", "Kanaskat-Palmer")]) {
  const onSelect = vi.fn();
  render(<MapSheet places={places} searchKey={{}} selection={createSelectionStore()} onSelect={onSelect} />);
  return { onSelect, launcher: () => screen.queryByRole("button", { name: "Map" }) };
}

describe("MapSheet", () => {
  test("a Map button, and no map loaded until it's pressed", () => {
    mapMounts.mockClear();
    const { launcher } = setup();
    expect(launcher()).toHaveAttribute("aria-haspopup", "dialog");
    expect(launcher()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mapMounts).not.toHaveBeenCalled();
  });

  test("no button when no place has coordinates", () => {
    const { launcher } = setup([place("1", "Somewhere", false)]);
    expect(launcher()).not.toBeInTheDocument();
  });

  test("opens a modal sheet with the map, focus on the handle", async () => {
    const { launcher } = setup();
    await userEvent.click(launcher()!);
    const sheet = screen.getByRole("dialog", { name: "Map of results" });
    expect(sheet).toHaveAttribute("aria-modal", "true");
    expect(await within(sheet).findByTestId("results-map")).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Expand map" })).toHaveFocus();
    expect(sheet).toHaveTextContent("The list has the same places.");
    expect(launcher()).toHaveAttribute("aria-expanded", "true");
  });

  test("the handle is a button that toggles full height", async () => {
    const { launcher } = setup();
    await userEvent.click(launcher()!);
    const handle = screen.getByRole("button", { name: "Expand map" });
    expect(handle).toHaveAttribute("aria-expanded", "false");
    await userEvent.keyboard("{Enter}");
    expect(handle).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard(" ");
    expect(handle).toHaveAttribute("aria-expanded", "false");
  });

  test("Escape and Close shut it and return focus to the Map button", async () => {
    const { launcher } = setup();
    await userEvent.click(launcher()!);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher()).toHaveFocus();
    await userEvent.click(launcher()!);
    await userEvent.click(screen.getByRole("button", { name: "Close map" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher()).toHaveFocus();
  });
});
