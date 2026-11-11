import { describe, test, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams } from "../api";
import { FullGroup } from "../results/FullGroup";
import { WatchContext } from "../results/watchContext";

const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};

const place = (name: string, drive: number | null, extra: Partial<CampgroundResult> = {}) =>
  ({ facility_id: name, name, booking_system: "recgov", estimated_drive_minutes: drive, windows: [],
    not_released_ranges: [{ start: "2027-06-01", end: "2027-06-30", releases_on: "2026-12-01" }],
    ...extra }) as CampgroundResult;

describe("FullGroup", () => {
  test("lists places closest first with what's in the way and the alert that would help", () => {
    render(<FullGroup params={juneWeekends} places={[
      place("Turlo", 88),
      place("Wallace Falls", 88, { booking_system: "wa_state", not_released_ranges: [] }),
      place("Kachess", 77),
    ]} />);
    const group = screen.getByRole("region", { name: "Full or not released yet" });
    expect(within(group).getByText("3 places")).toBeInTheDocument();
    const rows = within(group).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getByRole("heading", { level: 3 }).textContent))
      .toEqual(["Kachess", "Turlo", "Wallace Falls"]);
    expect(rows[0]).toHaveTextContent("~1h 17m drive · Recreation.gov");
    expect(rows[0]).toHaveTextContent("June opens Dec 4 – 25");
    expect(rows[2]).toHaveTextContent("Full all 4 weekends");
    expect(within(rows[2]).getByRole("button", { name: "Watch: Wallace Falls" })).toBeInTheDocument();
  });

  test("the alerts are stubs: disabled, and the note says they're coming", () => {
    render(<FullGroup params={juneWeekends} places={[place("Kachess", 77)]} />);
    const remind = screen.getByRole("button", { name: "Remind me: Kachess" });
    expect(remind).toHaveAttribute("aria-disabled", "true");
    expect(remind).toHaveAccessibleDescription(/coming soon/);
  });

  test("a place taking no reservations gets no alert button", () => {
    render(<FullGroup params={juneWeekends} places={[place("Tinkham", 54, {
      not_released_ranges: [], closed_ranges: [{ start: "2027-06-01", end: "2027-06-30" }],
    })]} />);
    expect(screen.getByRole("region", { name: "Nothing to book" })).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent("Not reservable these weekends");
    expect(screen.queryByRole("button", { name: /Tinkham/ })).not.toBeInTheDocument();
  });

  test("past six places the rest wait behind a button", async () => {
    render(<FullGroup params={juneWeekends}
      places={Array.from({ length: 9 }, (_, i) => place(`P${i}`, 60 + i))} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
    await userEvent.click(screen.getByRole("button", { name: "Show 3 more" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
  });

  test("renders nothing with nothing to list", () => {
    const { container } = render(<FullGroup params={juneWeekends} places={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("inside results, Watch opens the Watch sheet and Remind me its reminder mode", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 11, 9));
    const openWatch = vi.fn();
    const full = place("Wallace Falls", 88, { not_released_ranges: [] });
    const nyr = place("Kachess", 77);
    render(
      <WatchContext.Provider value={openWatch}>
        <FullGroup params={juneWeekends} places={[full, nyr]} />
      </WatchContext.Provider>,
    );
    const watch = screen.getByRole("button", { name: "Watch: Wallace Falls" });
    expect(watch).not.toHaveAttribute("aria-disabled");
    await userEvent.click(watch);
    expect(openWatch).toHaveBeenCalledWith(full, undefined, "full_group");
    const remind = screen.getByRole("button", { name: "Remind me: Kachess" });
    expect(remind).not.toHaveAttribute("aria-disabled");
    await userEvent.click(remind);
    expect(openWatch).toHaveBeenLastCalledWith(nyr, undefined, "full_group", "remind");
    expect(screen.getByText(/or get a reminder the morning booking opens/)).toBeInTheDocument();
    vi.useRealTimers();
  });

  test("inside results, no Remind me without a release date still ahead", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2027, 0, 1, 9));
    render(
      <WatchContext.Provider value={vi.fn()}>
        <FullGroup params={juneWeekends} places={[
          place("Kachess", 77),
          place("Turlo", 88, { not_released_ranges: [{ start: "2027-06-01", end: "2027-06-30", releases_on: null }] }),
        ]} />
      </WatchContext.Provider>,
    );
    expect(screen.queryByRole("button", { name: /Remind me/ })).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});
