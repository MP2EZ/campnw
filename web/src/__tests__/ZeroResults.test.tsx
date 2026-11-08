import { describe, test, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams, SearchResponse } from "../api";
import { ZeroResults } from "../results/ZeroResults";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), track: vi.fn() }));

// Far enough ahead that June 2032 is unreleased whenever this runs.
const params: SearchParams = {
  start_date: "2032-06-01", end_date: "2032-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
  from_location: "seattle", max_drive: 120,
};
const place = (name: string, drive: number) => ({
  facility_id: name, name, booking_system: "recgov", estimated_drive_minutes: drive, windows: [],
  total_available_sites: 0,
  not_released_ranges: [{ start: "2032-06-01", end: "2032-06-30", releases_on: "2031-12-01" }],
}) as unknown as CampgroundResult;
const results: SearchResponse = {
  campgrounds_checked: 2, campgrounds_with_availability: 0, results: [],
  warnings: [{ kind: "waf_blocked", count: 9, source: "wa_state", message: "" }],
};

describe("ZeroResults", () => {
  test("not released: says so, when each weekend opens, and lists the places", () => {
    render(<ZeroResults results={results} places={[place("Kachess", 77), place("Turlo", 88)]}
      params={params} onSearch={() => {}} />);
    expect(screen.getByText(/aren’t full\. Their June weekends just haven’t opened/)).toHaveTextContent(
      /WA State Parks couldn’t be checked right now/,
    );
    const timeline = screen.getByRole("region", { name: "When each weekend opens" });
    const items = within(timeline).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Jun 4 – 6");
    expect(items[0]).toHaveTextContent("7:00 am PT");
    expect(within(timeline).getByRole("button", { name: /Remind me on release mornings/ }))
      .toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("region", { name: "Not released yet" })).toHaveTextContent("Kachess");
  });

  test("a camp-sooner option runs its search", async () => {
    const onSearch = vi.fn();
    render(<ZeroResults results={results} places={[place("Kachess", 77)]} params={params} onSearch={onSearch} />);
    const sooner = screen.getByRole("region", { name: "Or camp sooner" });
    await userEvent.click(within(sooner).getByRole("button", { name: /Search released dates/ }));
    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({ from_location: "seattle", days_of_week: "4,5,6" }), "find");
  });
});
