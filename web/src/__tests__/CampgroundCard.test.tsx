import { describe, test, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams, Window } from "../api";
import { CampgroundCard } from "../results/CampgroundCard";

const track = vi.fn();
vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), track: (...a: unknown[]) => track(...a) }));

const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};

const win = (site: string, start: string, end: string, fit: Partial<Window> = {}): Window => ({
  campsite_id: site, site_name: site, loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, is_fcfs: false, booking_url: null,
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null, ...fit,
});

const dashPoint = {
  facility_id: "-2147483624", name: "Dash Point State Park", state: "WA", region: "Federal Way, WA",
  booking_system: "wa_state", latitude: 47.3, longitude: -122.4, total_available_sites: 6, fcfs_sites: 7,
  tags: ["beach", "boat-in"], estimated_drive_minutes: 48, availability_url: "https://wa.example/dash",
  elevator_pitch: "Puget Sound beach park.", error: null,
  weather_temp_high_f: 67, weather_temp_low_f: 50, weather_precip_pct: 10,
  windows: ["A", "B", "C", "D", "E", "F"].map((s) =>
    win(s, "2027-06-04", "2027-06-05", { fits_tent: true, fits_rv: true, max_rv_ft: 35 })),
} as CampgroundResult;

beforeEach(() => track.mockReset());

describe("CampgroundCard", () => {
  test("says where it is, what fits and how to book, per the design", () => {
    render(<CampgroundCard result={dashPoint} params={juneWeekends} rank={0} />);
    const card = screen.getByRole("article", { name: "Dash Point State Park" });
    expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent("Dash Point State Park");
    expect(card).toHaveTextContent("~48m drive");
    expect(card).toHaveTextContent("Federal Way, WA");
    expect(card).toHaveTextContent("Typical weather: Mid-June 67° / 50°");
    expect(card).toHaveTextContent("Puget Sound beach park.");
    expect(card).toHaveTextContent("Tent · RV ≤35′");
    expect(card).toHaveTextContent("Book via WA State Parks");
    expect(card).toHaveTextContent("+ 7 first-come, first-served sites");
    expect(within(card).getByRole("group", { name: "Weekends at Dash Point State Park" })).toBeInTheDocument();
  });

  test("the boat-in tag isn't repeated in the tag line", () => {
    render(<CampgroundCard result={dashPoint} params={juneWeekends} rank={0} />);
    expect(screen.getByText("beach")).toBeInTheDocument();
    expect(screen.queryByText(/boat-in/)).not.toBeInTheDocument();
  });

  test("rain shows when it's likely", () => {
    render(<CampgroundCard result={{ ...dashPoint, weather_precip_pct: 40 }} params={juneWeekends} rank={0} />);
    expect(screen.getByText(/Mid-June 67° \/ 50° · 40% rain/)).toBeInTheDocument();
  });

  test("a chip opens its sites (window_chip_opened); booking there is a book_click from the site panel", async () => {
    render(<CampgroundCard result={dashPoint} params={juneWeekends} rank={3} />);
    await userEvent.click(screen.getByRole("button", { name: /see open sites$/ }));
    expect(track).toHaveBeenCalledWith("window_chip_opened", {
      facility_id: "-2147483624", result_rank: 3, source: "wa_state", sites_in_chip: 6, nights: 3,
      chip_start: "2027-06-04", ui_version: "v2",
    });
    const dialog = screen.getByRole("dialog", { name: "Dash Point State Park" });
    await userEvent.click(within(dialog).getByRole("link", { name: /^Book on WA State Parks/ }));
    expect(track).toHaveBeenCalledWith("book_click", expect.objectContaining({
      facility_id: "-2147483624", result_rank: 3, from: "site_panel", type: "site", site_kind: "rv",
      sites_in_chip: 6, source: "wa_state", ui_version: "v2",
    }));
  });

  test("a boat-in place says so instead of a drive time", () => {
    render(<CampgroundCard result={{ ...dashPoint, boat_in: true, estimated_drive_minutes: 85 }}
      params={juneWeekends} rank={0} />);
    expect(screen.getByText("Boat-in only")).toBeInTheDocument();
    expect(screen.queryByText(/drive$/)).not.toBeInTheDocument();
  });

  test("no fit data says so", () => {
    const unknown = { ...dashPoint, fcfs_sites: 0, windows: [win("A", "2027-06-04", "2027-06-05")] };
    render(<CampgroundCard result={unknown} params={juneWeekends} rank={0} />);
    expect(screen.getByText("Site types not listed yet")).toBeInTheDocument();
    expect(screen.queryByText(/first-come/)).not.toBeInTheDocument();
  });

  test("shows the first photo, decorative, and falls back to a drawn tile if it fails", () => {
    const { container } = render(<CampgroundCard result={{ ...dashPoint, image_urls: ["https://cdn.recreation.gov/a.jpg"] }}
      params={juneWeekends} rank={0} />);
    const img = container.querySelector(".rv2-thumb img")!;
    expect(img).toHaveAttribute("alt", "");
    fireEvent.error(img);
    expect(container.querySelector(".rv2-thumb img")).toBeNull();
    expect(container.querySelector(".rv2-thumb svg")).toHaveAttribute("aria-hidden", "true");
  });
});
