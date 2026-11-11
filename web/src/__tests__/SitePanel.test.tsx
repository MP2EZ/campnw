import { describe, expect, test, vi } from "vitest";
import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams, Window } from "../api";
import { SitePanel } from "../results/SitePanel";

const weekends: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5",
};
const unknown = { fits_tent: null, fits_van: null, fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null };
const win = (site: string, extra: Partial<Window> = {}): Window => ({
  campsite_id: site, site_name: site, loop: "Main", campsite_type: "STANDARD",
  start_date: "2027-06-18", end_date: "2027-06-19", nights: 2, max_people: 8, max_people_known: true, is_fcfs: false,
  booking_url: `https://washington.goingtocamp.com/create-booking/results?mapId=-1&startDate=2027-06-18&endDate=2027-06-20&nights=2&isReserving=true&s=${site}`,
  ...unknown, ...extra,
});
const fortEbey = {
  facility_id: "-2147483616", name: "Fort Ebey State Park", booking_system: "wa_state",
  estimated_drive_minutes: 129, region: "Whidbey Island", availability_url: null,
  windows: [
    win("7", { fits_tent: true, fits_van: true, fits_rv: true, max_rv_ft: 30, hookups: false, walk_in: false }),
    win("27", { fits_tent: true, fits_van: true, fits_rv: true, max_rv_ft: 30, hookups: true, walk_in: false }),
    win("9", { fits_tent: true, fits_van: false, fits_rv: false, hookups: false, walk_in: false }),
    win("40", { max_people_known: false, start_date: "2027-06-19" }),
  ],
} as CampgroundResult;
const chip = { start: "2027-06-18", end: "2027-06-19" };

/** A chip button that opens the panel, like a card does. */
function Harness({ onBook = vi.fn() }: { onBook?: (...a: unknown[]) => void }) {
  const [opener, setOpener] = useState<HTMLElement | null>(null);
  return (
    <>
      <button type="button" onClick={(e) => setOpener(e.currentTarget)}>Fri 18 – Sat 19, 4 left</button>
      {opener && <SitePanel result={fortEbey} chip={chip} params={weekends} returnFocus={opener}
        onClose={() => setOpener(null)} onBook={onBook} />}
    </>
  );
}

async function open(onBook = vi.fn()) {
  render(<Harness onBook={onBook} />);
  await userEvent.click(screen.getByRole("button", { name: /Fri 18/ }));
  return screen.getByRole("dialog", { name: "Fort Ebey State Park" });
}

describe("SitePanel", () => {
  test("a modal dialog named for the place, with the stay and focus inside", async () => {
    const dialog = await open();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    expect(dialog).toHaveTextContent("Fri Jun 18 → Sun Jun 20 · 2 nights");
    expect(dialog).toHaveTextContent("~2h 9m drive · Whidbey Island");
    expect(dialog).toHaveTextContent("4 sites left for these nights.");
  });

  test("sites grouped by type, each a radio named for what it offers", async () => {
    const dialog = await open();
    const groups = within(dialog).getAllByRole("group");
    expect(groups.map((g) => g.querySelector("legend")?.textContent)).toEqual([
      "Tent and van sites, 1 open", "RV and trailer sites, 2 open", "Site types not listed yet, 1 open",
    ]);
    expect(within(groups[1]).getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual([
      "Site 7, Tent, van or RV up to 30′, Loop Main · up to 8 people",
      "Site 27, Tent, van or RV up to 30′, Loop Main · up to 8 people, Hookups",
    ]);
  });

  test("unknown fit and capacity aren't made up", async () => {
    const dialog = await open();
    const unlisted = within(dialog).getByRole("radio", { name: /^Site 40/ });
    // The group's legend says "Site types not listed yet"; the row doesn't repeat it.
    expect(unlisted).toHaveAccessibleName("Site 40, Loop Main · Sat night only");
    expect(unlisted.closest("fieldset")?.querySelector("legend")).toHaveTextContent(/^Site types not listed yet/);
  });

  test("the first site is chosen; picking another changes the link and the copy", async () => {
    const onBook = vi.fn();
    const dialog = await open(onBook);
    expect(within(dialog).getByRole("radio", { name: /^Site 9,/ })).toBeChecked();
    await userEvent.click(within(dialog).getByRole("radio", { name: /^Site 27,/ }));
    const book = within(dialog).getByRole("link", { name: /^Book on WA State Parks/ });
    expect(book).toHaveAccessibleName("Book on WA State Parks, site 27 (opens in a new tab)");
    expect(book).toHaveAttribute("href", expect.stringContaining("s=27"));
    expect(book).toHaveAttribute("target", "_blank");
    expect(dialog).toHaveTextContent("Opens WA State Parks in a new tab at Loop Main with Jun 18–20 filled in. Find site 27 there");
    expect(dialog).toHaveTextContent("Someone else can book the site before you finish.");
    await userEvent.click(book);
    expect(onBook).toHaveBeenCalledWith(expect.objectContaining({ id: "27", hookups: true }), 4);
  });

  test("Escape closes and focus goes back to the chip", async () => {
    await open();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Fri 18/ })).toHaveFocus();
  });

  test("Close and a tap outside close it too", async () => {
    const dialog = await open();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Fri 18/ }));
    await userEvent.click(screen.getByRole("dialog").parentElement!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("Tab stays inside: Close, the chosen site, Book, and round again", async () => {
    const dialog = await open();
    await userEvent.tab();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await userEvent.tab();
    expect(within(dialog).getByRole("radio", { name: /^Site 9,/ })).toHaveFocus();
    await userEvent.tab();
    expect(within(dialog).getByRole("link", { name: /^Book on/ })).toHaveFocus();
    await userEvent.tab();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(within(dialog).getByRole("link", { name: /^Book on/ })).toHaveFocus();
  });
});
