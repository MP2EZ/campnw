import { describe, test, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult } from "../api";
import { DriveBands } from "../results/DriveBands";

vi.mock("../results/CampgroundCard", () => ({
  CampgroundCard: ({ result, rank }: { result: CampgroundResult; rank: number }) => (
    <article aria-label={result.name} data-rank={rank} />
  ),
}));

const place = (name: string, drive: number | null, boat = false) =>
  ({ facility_id: name, name, estimated_drive_minutes: drive, boat_in: boat }) as CampgroundResult;

const names = (el: HTMLElement) => within(el).queryAllByRole("article").map((a) => a.getAttribute("aria-label"));

describe("DriveBands", () => {
  test("a titled section per drive band, nearest first, boat-in last with its note", () => {
    render(<DriveBands params={null} results={[
      place("Blake Island", null, true), place("Schafer", 128), place("Dash Point", 48), place("Lake Easton", 79),
    ]} />);
    const sections = screen.getAllByRole("region");
    expect(sections.map((s) => s.getAttribute("aria-labelledby"))).toEqual([
      "rv2-band-h0", "rv2-band-h1", "rv2-band-h2", "rv2-band-boat-in",
    ]);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Under 1 hour", "1–2 hours", "2–3 hours", "Boat-in only",
    ]);
    expect(within(sections[0]).getByText("1 place")).toBeInTheDocument();
    expect(names(sections[3])).toEqual(["Blake Island"]);
    expect(sections[3]).toHaveTextContent("No road access.");
  });

  test("ranks follow the order on screen", () => {
    render(<DriveBands params={null} results={[place("Far", 130), place("Near", 20), place("Mid", 70)]} />);
    expect(screen.getAllByRole("article").map((a) => [a.getAttribute("aria-label"), a.dataset.rank]))
      .toEqual([["Near", "0"], ["Mid", "1"], ["Far", "2"]]);
  });

  test("a long band shows five and a button for the rest", async () => {
    const many = Array.from({ length: 8 }, (_, i) => place(`P${i}`, 60 + i));
    render(<DriveBands params={null} results={many} />);
    const band = screen.getByRole("region", { name: "1–2 hours" });
    expect(within(band).getByText("8 places")).toBeInTheDocument();
    expect(names(band)).toHaveLength(5);
    await userEvent.click(within(band).getByRole("button", { name: "Show 3 more within 1–2 hours" }));
    expect(names(band)).toHaveLength(8);
    expect(within(band).getByRole("button", { name: "Show fewer" })).toHaveAttribute("aria-expanded", "true");
  });

  test("six in a band are all shown: no button for one card", () => {
    render(<DriveBands params={null} results={Array.from({ length: 6 }, (_, i) => place(`P${i}`, 10 + i))} />);
    expect(screen.getAllByRole("article")).toHaveLength(6);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("without a starting point there are no bands to name", () => {
    render(<DriveBands params={null} results={[place("A", null), place("B", null)]} />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });
});
