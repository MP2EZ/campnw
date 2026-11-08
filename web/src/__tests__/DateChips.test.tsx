import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateChips } from "../results/DateChips";
import SearchBar from "../results/SearchBar";
import { SearchContext, type SearchContextValue } from "../contexts/SearchContext";
import type { SearchParams } from "../api";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), track: vi.fn() }));

const JUNE: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2,
  days_of_week: "4,5,6", from_location: "seattle", max_drive: 180, tags: "lakeside",
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-07T12:00:00"));
});
afterEach(() => vi.useRealTimers());

describe("DateChips", () => {
  test("offers this weekend, next weekend, the searched month and Pick dates", () => {
    render(<DateChips params={JUNE} onSearch={() => {}} />);
    const group = screen.getByRole("group", { name: "Dates" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "This weekend", "Next weekend", "June weekends, 2027", "Pick dates",
    ]);
    expect(within(group).getByRole("button", { name: "June weekends, 2027" })).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: "This weekend" })).toHaveAttribute("aria-pressed", "false");
  });

  test("a chip searches its dates and keeps the rest of the search", async () => {
    const onSearch = vi.fn();
    render(<DateChips params={JUNE} onSearch={onSearch} />);
    await userEvent.click(screen.getByRole("button", { name: "Next weekend" }));
    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({
      start_date: "2026-11-13", end_date: "2026-11-15", from_location: "seattle", max_drive: 180, tags: "lakeside",
    }), "find");
  });

  test("the pressed chip doesn't search again", async () => {
    const onSearch = vi.fn();
    render(<DateChips params={JUNE} onSearch={onSearch} />);
    await userEvent.click(screen.getByRole("button", { name: "June weekends, 2027" }));
    expect(onSearch).not.toHaveBeenCalled();
  });

  test("nothing before there's a search", () => {
    const { container } = render(<DateChips params={null} onSearch={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("Pick dates opens the search sheet at When", async () => {
    const ctx: SearchContextValue = {
      results: null, loading: false, searchDates: null, searchParams: JUNE, sourceFilter: new Set(), filteredResults: [],
    };
    render(
      <SearchContext.Provider value={ctx}>
        <SearchBar onSearch={() => {}} onAsk={() => {}} />
        <DateChips params={JUNE} onSearch={() => {}} />
      </SearchContext.Provider>,
    );
    await act(() => userEvent.click(screen.getByRole("button", { name: "Pick dates" })));
    const sheet = screen.getByRole("dialog", { name: "Edit search" });
    const when = within(sheet).getByRole("region", { name: "When" });
    await waitFor(() => expect(when).toContainElement(document.activeElement as HTMLElement));
    expect(document.activeElement).toHaveAttribute("aria-pressed", "true");
  });
});
