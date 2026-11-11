import { describe, test, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams, Window } from "../api";
import { buildWindowChips } from "../results/chips";
import { WindowChips } from "../results/WindowChips";

const juneWeekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
};

const win = (site: string, start: string, end: string): Window => ({
  campsite_id: site, site_name: site, loop: "", campsite_type: "STANDARD",
  start_date: start, end_date: end, nights: 2, max_people: 6, is_fcfs: false, booking_url: null,
  fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null,
});

const place = (windows: Window[], url: string | null = "https://wa.example/dash") =>
  ({ facility_id: "1", name: "Dash Point", availability_url: url, windows }) as CampgroundResult;

function renderChips(windows: Window[], params: SearchParams = juneWeekends, url?: string | null) {
  const onOpen = vi.fn();
  const result = place(windows, url);
  render(<WindowChips chips={buildWindowChips(result, params)} name="Dash Point" params={params} onOpen={onOpen} />);
  return onOpen;
}

const six = ["A", "B", "C", "D", "E", "F"];

describe("WindowChips", () => {
  test("one button per weekend, named for the dates and count, that opens its sites", () => {
    renderChips(["04", "11"].flatMap((d) => six.map((s) =>
      win(s, `2027-06-${d}`, `2027-06-${String(Number(d) + 2).padStart(2, "0")}`))));
    const group = screen.getByRole("group", { name: "Weekends at Dash Point" });
    const chips = within(group).getAllByRole("button", { name: /see open sites$/ });
    expect(chips.map((c) => c.textContent)).toEqual([
      "Fri 4 – Sun 6, 6 open, see open sites",
      "Fri 11 – Sun 13, 6 open, see open sites",
    ]);
    expect(chips[0]).toHaveAccessibleName("Fri 4 – Sun 6, 6 open, see open sites");
    expect(chips[0]).toHaveAttribute("aria-haspopup", "dialog");
  });

  test("few left is said in words and marked with a hidden dot, not colour alone", () => {
    renderChips([win("A", "2027-06-04", "2027-06-05"), win("B", "2027-06-04", "2027-06-05")]);
    const chip = screen.getByRole("button", { name: /^Fri 4 – Sun 6, 2 left/ });
    expect(chip.querySelector(".rv2-chip-dot")).toHaveAttribute("aria-hidden", "true");
  });

  test("a click opens the chip's sites, handing over the chip to return focus to", async () => {
    const onOpen = renderChips(six.map((s) => win(s, "2027-06-04", "2027-06-05")));
    const chip = screen.getByRole("button", { name: /^Fri 4 – Sun 6/ });
    await userEvent.click(chip);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ start: "2027-06-04", open: 6 }), chip);
  });

  test("more stays than fit stay behind a button that shows them", async () => {
    const days = ["01", "03", "05", "07", "09", "11"];
    renderChips(days.map((d) => win(d, `2027-06-${d}`, `2027-06-${d}`)),
      { ...juneWeekends, days_of_week: undefined, nights: 1 });
    expect(screen.getByRole("group", { name: "1-night stays at Dash Point" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /see open sites$/ })).toHaveLength(4);
    const more = screen.getByRole("button", { name: "+2 more" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(more);
    expect(screen.getAllByRole("button", { name: /see open sites$/ })).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Show fewer" })).toHaveAttribute("aria-expanded", "true");
  });

  test("exact dates are one chip, labelled as the user's dates", () => {
    renderChips([win("A", "2027-06-04", "2027-06-06")],
      { start_date: "2027-06-04", end_date: "2027-06-06", mode: "exact", nights: 2 });
    const group = screen.getByRole("group", { name: "Your dates at Dash Point" });
    expect(within(group).getAllByRole("button", { name: /see open sites$/ })).toHaveLength(1);
  });

  test("with a Watch sheet, a full weekend is a button that opens it; not-released stays text", async () => {
    const onWatch = vi.fn();
    const result = {
      ...place(six.map((s) => win(s, "2027-06-04", "2027-06-06"))),
      not_released_ranges: [{ start: "2027-06-25", end: "2027-06-27", releases_on: "2026-12-25" }],
    } as CampgroundResult;
    render(<WindowChips chips={buildWindowChips(result, juneWeekends)} name="Dash Point" params={juneWeekends}
      source="WA State Parks" onBook={vi.fn()} onWatch={onWatch} />);
    const watch = screen.getByRole("button", { name: "Fri 11 – Sun 13, Full · Watch" });
    await userEvent.click(watch);
    expect(onWatch).toHaveBeenCalledWith(expect.objectContaining({ start: "2027-06-11", status: "full" }));
    expect(screen.queryByRole("button", { name: /Fri 25/ })).not.toBeInTheDocument();
  });

  test("with reminders, a not-released weekend with a release date is a button that opens one", async () => {
    const onRemind = vi.fn();
    const result = {
      ...place(six.map((s) => win(s, "2027-06-04", "2027-06-06"))),
      not_released_ranges: [{ start: "2027-06-18", end: "2027-06-27", releases_on: "2026-12-18" }],
    } as CampgroundResult;
    render(<WindowChips chips={buildWindowChips(result, juneWeekends)} name="Dash Point" params={juneWeekends}
      source="WA State Parks" onBook={vi.fn()} onRemind={onRemind} remindStarts={new Set(["2027-06-25"])} />);
    await userEvent.click(screen.getByRole("button", { name: "Fri 25 – Sun 27, Opens Dec 25 · Remind me" }));
    expect(onRemind).toHaveBeenCalledWith(expect.objectContaining({ start: "2027-06-25", status: "not_released" }));
    // Not in remindStarts (e.g. its release date has passed): text only.
    expect(screen.queryByRole("button", { name: /Fri 18/ })).not.toBeInTheDocument();
    expect(screen.getByText("Fri 18 – Sun 20")).toBeInTheDocument();
  });
});

