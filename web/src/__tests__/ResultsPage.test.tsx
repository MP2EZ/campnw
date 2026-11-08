import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { CampgroundResult, SearchResponse } from "../api";
import { SearchContext, type SearchContextValue } from "../contexts/SearchContext";
import ResultsPage from "../results/ResultsPage";

vi.mock("../components/ResultCard", () => ({
  ResultCard: ({ result }: { result: CampgroundResult }) => <article>{result.name}</article>,
}));
vi.mock("../components/SmartZeroState", () => ({
  SmartZeroState: () => <div>zero state</div>,
}));

const place = (name: string, open: number) =>
  ({ facility_id: name, name, booking_system: "wa_state", total_available_sites: open }) as CampgroundResult;

const results: SearchResponse = {
  campgrounds_checked: 20,
  campgrounds_matched: 46,
  campgrounds_with_availability: 2,
  results: [place("Dash Point", 12), place("Lake Easton", 3), place("Kachess", 0)],
  warnings: [{ kind: "waf_blocked", count: 9, source: "or_state",
    message: "Oregon State Parks results unavailable — the booking site is blocking requests." }],
  not_released_campgrounds: 18,
  releases_on_earliest: "2026-12-04",
  releases_on_latest: "2026-12-25",
};

function renderPage(overrides: Partial<SearchContextValue> = {}) {
  const ctx: SearchContextValue = {
    results,
    loading: false,
    searchDates: { start: "2027-06-01", end: "2027-06-30" },
    searchParams: { start_date: "2027-06-01", end_date: "2027-06-30", nights: 2,
      days_of_week: "4,5,6", from_location: "seattle", max_drive: 180 },
    sourceFilter: new Set(["wa_state"]),
    filteredResults: results.results,
    ...overrides,
  };
  return render(
    <SearchContext.Provider value={ctx}>
      <ResultsPage maxResults={20} onCheckRest={() => {}} completedAt={Date.now()} onSearch={() => {}} />
    </SearchContext.Provider>,
  );
}

describe("ResultsPage", () => {
  test("answers first, then coverage, notices and the open places", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "2 campgrounds have a June weekend open within 3 hours of Seattle.",
    );
    expect(screen.getByText(/Checked 20 of 46 nearby campgrounds/)).toHaveTextContent(/searched just now/);
    expect(screen.getByRole("note")).toHaveTextContent(
      "18 campgrounds haven't released these dates yet. Booking typically opens Dec 4 – 25.",
    );
    expect(screen.getByText(/Oregon State Parks results unavailable/)).toBeInTheDocument();
    expect(screen.getAllByRole("article").map((a) => a.textContent)).toEqual(["Dash Point", "Lake Easton"]);
    expect(screen.queryByText("zero state")).not.toBeInTheDocument();
  });

  test("uses the v2 container the heading font is scoped to", () => {
    const { container } = renderPage();
    expect(container.querySelector("section.results-v2")).toHaveAccessibleName(/2 campgrounds have/);
  });

  test("while streaming it shows no timestamp and no zero state", () => {
    renderPage({ loading: true, filteredResults: [] });
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/^Checking campgrounds for a June weekend/);
    expect(screen.queryByText(/searched/)).not.toBeInTheDocument();
    expect(screen.queryByText("zero state")).not.toBeInTheDocument();
  });

  test("no notices when everything was released and checked", () => {
    renderPage({ results: { ...results, warnings: [], not_released_campgrounds: 0 } });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});
