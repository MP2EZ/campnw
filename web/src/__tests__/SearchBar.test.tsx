import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchBar from "../results/SearchBar";
import { SearchContext, type SearchContextValue } from "../contexts/SearchContext";
import type { SearchParams } from "../api";

const findCampgrounds = vi.fn();
vi.mock("../api", async (orig) => ({
  ...(await orig<typeof import("../api")>()),
  findCampgrounds: (...a: unknown[]) => findCampgrounds(...a),
  track: vi.fn(),
}));

const JUNE: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2,
  days_of_week: "4,5,6", from_location: "seattle", max_drive: 180, people: 2, equipment: "tent",
};

function ctx(searchParams: SearchParams | null): SearchContextValue {
  return { results: null, loading: false, searchDates: null, searchParams, sourceFilter: new Set(), filteredResults: [] };
}

function setup(params: SearchParams | null = JUNE) {
  const onSearch = vi.fn();
  const onAsk = vi.fn();
  const ui = (p: SearchParams | null) => (
    <SearchContext.Provider value={ctx(p)}>
      <SearchBar onSearch={onSearch} onAsk={onAsk} />
    </SearchContext.Provider>
  );
  const view = render(ui(params));
  const bar = screen.getByRole("search", { name: "Campsite search" });
  const segment = (name: RegExp) => within(bar).getByRole("button", { name });
  return { onSearch, onAsk, bar, segment, rerender: (p: SearchParams | null) => view.rerender(ui(p)) };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-07T12:00:00"));
  findCampgrounds.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("SearchBar", () => {
  test("shows the current search in its segments", () => {
    const { segment } = setup();
    expect(segment(/^Where/)).toHaveTextContent("Near Seattle");
    expect(segment(/^When/)).toHaveTextContent("Weekends in June · 2 nights");
    expect(segment(/^Who/)).toHaveTextContent("2 people · Tent");
    expect(segment(/^Drive/)).toHaveTextContent("Up to 3 h");
  });

  test("before a search, shows the defaults", () => {
    const { segment } = setup(null);
    expect(segment(/^When/)).toHaveTextContent("Next weekend · 2 nights");
    expect(segment(/^Drive/)).toHaveTextContent("Any distance");
  });

  test("a popover is a dialog: focus moves in, Escape closes and returns focus", async () => {
    const user = userEvent.setup();
    const { segment } = setup();
    await user.click(segment(/^When/));
    const dialog = screen.getByRole("dialog", { name: "When" });
    expect(segment(/^When/)).toHaveAttribute("aria-expanded", "true");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(segment(/^When/)).toHaveFocus();
  });

  test("a click outside closes the popover", async () => {
    const user = userEvent.setup();
    const { segment } = setup();
    await user.click(segment(/^Who/));
    await user.click(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("edits a draft and searches on submit", async () => {
    const user = userEvent.setup();
    const { segment, onSearch } = setup();
    await user.click(segment(/^When/));
    await user.click(screen.getByRole("button", { name: "This weekend" }));
    await user.click(screen.getByRole("button", { name: "Long weekends" }));
    await user.click(screen.getByRole("button", { name: "More nights" }));
    expect(onSearch).not.toHaveBeenCalled();
    expect(segment(/^When/)).toHaveTextContent("This weekend · 3 nights");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Search" }));
    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({
      start_date: "2026-11-07", end_date: "2026-11-08", days_of_week: "3,4,5,6", nights: 3, max_drive: 180,
    }), "find");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("exact dates search in exact mode", async () => {
    const user = userEvent.setup();
    const { segment, bar, onSearch } = setup();
    await user.click(segment(/^When/));
    await user.click(screen.getByRole("button", { name: "Exact dates" }));
    expect(screen.getByLabelText("Arrive")).toHaveValue("2026-11-21");
    expect(screen.getByLabelText("Leave")).toHaveValue("2026-11-23");
    await user.click(within(bar).getAllByRole("button", { name: "Search" })[0]);
    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({
      start_date: "2026-11-21", end_date: "2026-11-23", mode: "exact", nights: 2,
    }), "exact");
  });

  test("who: people and a trailer length, carried but labelled as not filtering yet", async () => {
    const user = userEvent.setup();
    const { segment, bar, onSearch } = setup();
    await user.click(segment(/^Who/));
    await user.click(screen.getByRole("button", { name: "More people" }));
    await user.click(screen.getByRole("button", { name: "Trailer or RV" }));
    await user.selectOptions(screen.getByLabelText("Length"), "30");
    expect(screen.getByText(/don’t filter results yet/)).toBeInTheDocument();
    expect(segment(/^Who/)).toHaveTextContent("3 people · 30′ trailer");
    await user.click(within(bar).getAllByRole("button", { name: "Search" })[0]);
    expect(onSearch.mock.calls[0][0]).toMatchObject({ people: 3, equipment: "trailer", rig_length: 30 });
  });

  test("typeahead: a combobox that picks a campground, which drops the drive cap", async () => {
    const user = userEvent.setup();
    findCampgrounds.mockResolvedValue([
      { facility_id: "1", name: "Ohanapecosh", state: "WA", region: "Mt Rainier", booking_system: "recgov", drive_minutes_from_base: 140 },
      { facility_id: "2", name: "Ohop Lake", state: "WA", region: "", booking_system: "wa_state", drive_minutes_from_base: 70 },
    ]);
    const { segment, bar, onSearch } = setup();
    await user.click(segment(/^Where/));
    const box = screen.getByRole("combobox", { name: "Or a campground by name" });
    await user.type(box, "oh");
    await waitFor(() => expect(box).toHaveAttribute("aria-expanded", "true"));
    expect(findCampgrounds).toHaveBeenCalledTimes(1);
    expect(findCampgrounds.mock.calls[0][0]).toBe("oh");
    const list = screen.getByRole("listbox", { name: "Campgrounds" });
    expect(box).toHaveAttribute("aria-controls", list.id);
    expect(within(list).getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("2 campgrounds found");

    await user.keyboard("{ArrowDown}{ArrowDown}");
    const second = within(list).getByRole("option", { name: /Ohop Lake/ });
    expect(box).toHaveAttribute("aria-activedescendant", second.id);
    expect(second).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}{Enter}");
    expect(box).toHaveValue("Ohanapecosh");
    expect(box).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    expect(segment(/^Where/)).toHaveTextContent("Ohanapecosh");
    expect(segment(/^Drive/)).toHaveTextContent("Any distance");
    await user.click(within(bar).getAllByRole("button", { name: "Search" })[0]);
    expect(onSearch.mock.calls[0][0]).toMatchObject({ name: "Ohanapecosh" });
    expect(onSearch.mock.calls[0][0]).not.toHaveProperty("max_drive");
  });

  test("Escape in an open listbox closes only the listbox", async () => {
    const user = userEvent.setup();
    findCampgrounds.mockResolvedValue([
      { facility_id: "1", name: "Ohanapecosh", state: "WA", region: "", booking_system: "recgov", drive_minutes_from_base: 140 },
    ]);
    const { segment } = setup();
    await user.click(segment(/^Where/));
    const box = screen.getByRole("combobox", { name: "Or a campground by name" });
    await user.type(box, "oha");
    await waitFor(() => expect(box).toHaveAttribute("aria-expanded", "true"));
    await user.keyboard("{Escape}");
    expect(box).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("a June search far ahead still shows June as chosen", async () => {
    const user = userEvent.setup();
    const { segment } = setup({ ...JUNE, start_date: "2027-09-01", end_date: "2027-09-30" });
    await user.click(segment(/^When/));
    expect(screen.getByRole("button", { name: "September 2027" })).toHaveAttribute("aria-pressed", "true");
  });

  test("clearing the name returns focus to the name box", async () => {
    const user = userEvent.setup();
    const { segment } = setup({ ...JUNE, name: "Ohanapecosh" });
    await user.click(segment(/^Where/));
    await user.click(screen.getByRole("button", { name: "Clear name" }));
    const box = screen.getByRole("combobox", { name: "Or a campground by name" });
    expect(box).toHaveValue("");
    expect(box).toHaveFocus();
  });

  test("typing a name and searching without picking searches the text", async () => {
    const user = userEvent.setup();
    findCampgrounds.mockResolvedValue([]);
    const { segment, bar, onSearch } = setup();
    await user.click(segment(/^Where/));
    await user.type(screen.getByRole("combobox", { name: "Or a campground by name" }), "lake");
    await user.click(within(bar).getAllByRole("button", { name: "Search" })[0]);
    expect(onSearch.mock.calls[0][0]).toMatchObject({ name: "lake" });
  });

  test("Ask runs a plain-language search", async () => {
    const user = userEvent.setup();
    const { onAsk, onSearch } = setup();
    const ask = screen.getByRole("textbox", { name: "Or ask" });
    await user.type(ask, "lakes near Portland in July{Enter}");
    expect(onAsk).toHaveBeenCalledWith("lakes near Portland in July");
    expect(onSearch).not.toHaveBeenCalled();
    expect(ask).toHaveValue("");
  });

  test("follows a new search, e.g. what a question was parsed into", () => {
    const { segment, rerender } = setup();
    rerender({ start_date: "2027-07-01", end_date: "2027-07-31", nights: 1, from_location: "portland", tags: "lakeside" });
    expect(segment(/^Where/)).toHaveTextContent("Near Portland");
    expect(segment(/^When/)).toHaveTextContent("July · 1 night");
  });

  test("keeps filters the bar doesn't edit", async () => {
    const user = userEvent.setup();
    const { bar, onSearch } = setup({ ...JUNE, tags: "lakeside", state: "WA" });
    await user.click(within(bar).getAllByRole("button", { name: "Search" })[0]);
    expect(onSearch.mock.calls[0][0]).toMatchObject({ tags: "lakeside", state: "WA" });
  });

  test("mobile sheet: a modal dialog with every segment, Escape returns focus", async () => {
    const user = userEvent.setup();
    setup();
    const open = screen.getByRole("button", { name: /^Edit search: Weekends in June/ });
    expect(open).toHaveAccessibleName("Edit search: Weekends in June, Near Seattle · 2 people, tent · up to 3 h");
    await user.click(open);
    const sheet = screen.getByRole("dialog", { name: "Edit search" });
    expect(sheet).toHaveAttribute("aria-modal", "true");
    for (const name of ["Where", "When", "Who", "Drive"]) {
      expect(within(sheet).getByRole("region", { name })).toBeInTheDocument();
    }
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(open).toHaveFocus();
  });

  test("searching from the mobile sheet closes it", async () => {
    const user = userEvent.setup();
    const { onSearch } = setup();
    await user.click(screen.getByRole("button", { name: /^Edit search/ }));
    const sheet = screen.getByRole("dialog", { name: "Edit search" });
    await user.click(within(sheet).getByRole("button", { name: "Search" }));
    expect(onSearch).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
