import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams } from "../api";
import { QuickPicks } from "../results/QuickPicks";

const anyDay: SearchParams = { start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2 };
const place = (id: string, drive: number, sites: number) =>
  ({ facility_id: id, name: `Place ${id}`, booking_system: "recgov", estimated_drive_minutes: drive,
    total_available_sites: sites, tags: [], windows: [] }) as unknown as CampgroundResult;

describe("QuickPicks", () => {
  test("each pick is a link to its card that reports the pick", async () => {
    const onPick = vi.fn();
    render(<QuickPicks params={anyDay} onPick={onPick}
      results={[place("1", 30, 2), place("2", 60, 40), place("3", 90, 5)]} />);
    expect(screen.getByRole("heading", { name: "Quick picks" })).toBeInTheDocument();
    const closest = screen.getByRole("link", { name: /Closest Place 1/ });
    expect(closest).toHaveAttribute("href", "#rv2-card-1");
    expect(screen.getByRole("link", { name: /Most open sites Place 2 ~1h · 40 sites open/ })).toBeInTheDocument();
    await userEvent.click(closest);
    expect(onPick).toHaveBeenCalledWith("1");
  });

  test("one pick isn't a choice, so nothing renders", () => {
    const { container } = render(<QuickPicks params={anyDay} onPick={() => {}}
      results={[place("1", 30, 2), place("2", 60, 40)]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
