import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import App from "../App";
import ResultsPage from "../results/ResultsPage";
import { SearchContext, type SearchContextValue } from "../contexts/SearchContext";
import type { CampgroundResult, Window } from "../api";

expect.extend(toHaveNoViolations);

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    updateProfile: vi.fn(),
    refresh: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({ ok: true, json: async () => [] });
});

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

const mockSearchResults = [
  {
    facility_id: "232465",
    name: "Ohanapecosh",
    booking_system: "recgov",
    state: "WA",
    total_available_sites: 5,
    latitude: 46.73,
    longitude: -121.57,
    estimated_drive_minutes: 120,
    availability_url: "https://recreation.gov/camping/campgrounds/232465",
    windows: [
      { site_id: "1", site_name: "A1", start_date: "2026-06-01", end_date: "2026-06-03", nights: 2, booking_url: "#", is_fcfs: false },
    ],
    tags: ["riverside"],
  },
];

describe("Accessibility (axe-core)", () => {
  test("home page has no a11y violations", async () => {
    const { container } = renderRoute("/");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("home page with search results has no a11y violations", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
      headers: new Headers(),
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode(`data: ${JSON.stringify({ type: "result", data: mockSearchResults[0] })}\n\n`),
            })
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode(`data: ${JSON.stringify({ type: "done", data: { total: 1 } })}\n\n`),
            })
            .mockResolvedValueOnce({ done: true }),
          cancel: vi.fn(),
        }),
      },
    });
    const { container } = renderRoute("/");
    // Wait for any async rendering
    await new Promise((r) => setTimeout(r, 100));
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("map page has no a11y violations", async () => {
    const { container } = renderRoute("/map");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("plan page has no a11y violations", async () => {
    const { container } = renderRoute("/plan");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ── Results v2 (v1.48) ───────────────────────────────────────────────

const site = (id: string, start: string, end: string, fit: Partial<Window> = {}): Window => ({
  campsite_id: id, site_name: id, loop: "", campsite_type: "STANDARD", start_date: start, end_date: end,
  nights: 2, max_people: 6, is_fcfs: false, booking_url: null, fits_tent: true, fits_van: null,
  fits_rv: null, max_rv_ft: null, hookups: null, walk_in: null, ...fit,
});

const v2Place = (id: string, name: string, drive: number | null, extra: Partial<CampgroundResult> = {}) => ({
  facility_id: id, name, state: "WA", region: "Federal Way, WA", booking_system: "wa_state",
  latitude: 47.3, longitude: -122.4, total_available_sites: 3, fcfs_sites: 0, tags: ["beach"],
  estimated_drive_minutes: drive, availability_url: `https://wa.example/${id}`, error: null,
  weather_temp_high_f: 67, weather_temp_low_f: 50,
  windows: ["04", "11", "18", "25", "30"].flatMap((d, i) =>
    ["A", "B", "C"].slice(0, i + 1).map((s) => site(s, `2027-06-${d}`, `2027-06-${d}`))),
  ...extra,
}) as CampgroundResult;

function renderV2() {
  const results = [
    v2Place("1", "Dash Point State Park", 48),
    v2Place("2", "Kanaskat-Palmer State Park", 72, {
      windows: [site("A", "2027-06-04", "2027-06-04")],
      not_released_ranges: [{ start: "2027-06-25", end: "2027-06-30", releases_on: "2026-09-25" }],
    }),
    v2Place("3", "Blake Island State Park", null, { boat_in: true, tags: ["boat-in", "beach"] }),
  ];
  const ctx: SearchContextValue = {
    results: { campgrounds_checked: 4, campgrounds_with_availability: 3, results, warnings: [],
      unavailable: [v2Place("4", "Wallace Falls State Park", 88, { windows: [], total_available_sites: 0 })] },
    loading: false,
    searchDates: { start: "2027-06-01", end: "2027-06-30" },
    searchParams: { start_date: "2027-06-01", end_date: "2027-06-30", nights: 1, days_of_week: "4,5,6",
      from_location: "seattle", max_drive: 180 },
    sourceFilter: new Set(["wa_state"]),
    filteredResults: results,
  };
  return render(
    <SearchContext.Provider value={ctx}>
      <ResultsPage maxResults={20} onCheckRest={() => {}} completedAt={Date.now()} onSearch={() => {}} />
    </SearchContext.Provider>,
  );
}

describe("Accessibility: results v2", () => {
  test("cards, chips and groups have no axe violations", async () => {
    const { container } = renderV2();
    expect(await axe(container)).toHaveNoViolations();
  });

  test("quick picks render and pass axe", async () => {
    const { container } = renderV2();
    expect(screen.getByRole("heading", { name: "Quick picks" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  test("the zero-results page has no axe violations", async () => {
    const nyr = v2Place("9", "Kachess", 77, { windows: [], total_available_sites: 0, booking_system: "recgov",
      not_released_ranges: [{ start: "2027-06-01", end: "2027-06-30", releases_on: "2026-12-01" }] });
    const ctx: SearchContextValue = {
      results: { campgrounds_checked: 1, campgrounds_with_availability: 0, results: [], warnings: [], unavailable: [nyr] },
      loading: false,
      searchDates: { start: "2027-06-01", end: "2027-06-30" },
      searchParams: { start_date: "2027-06-01", end_date: "2027-06-30", nights: 2, days_of_week: "4,5,6" },
      sourceFilter: new Set(),
      filteredResults: [],
    };
    const { container } = render(
      <SearchContext.Provider value={ctx}>
        <ResultsPage maxResults={20} onCheckRest={() => {}} completedAt={Date.now()} onSearch={() => {}} />
      </SearchContext.Provider>,
    );
    expect(screen.getAllByRole("region", { name: /When each weekend opens|Not released yet/ })).toHaveLength(2);
    expect(await axe(container)).toHaveNoViolations();
  });

  test("full and not-released chips say so in words, not just a dashed border", () => {
    const { container } = renderV2();
    const full = [...container.querySelectorAll(".rv2-chip-full")];
    expect(full.length).toBeGreaterThan(0);
    for (const chip of full) expect(chip.textContent).toMatch(/Full|Opens|Not released/);
  });

  test("few is never colour alone: the chip says \u201cleft\u201d and the dot is hidden", () => {
    const { container } = renderV2();
    const few = [...container.querySelectorAll(".rv2-chip")].filter((c) => c.querySelector(".rv2-chip-dot"));
    expect(few.length).toBeGreaterThan(0);
    for (const chip of few) {
      expect(chip.textContent).toMatch(/\d+ left/);
      expect(chip.querySelector(".rv2-chip-dot")).toHaveAttribute("aria-hidden", "true");
    }
  });

  test("interactive targets are at least 44px tall", () => {
    const css = readFileSync(join(__dirname, "../results/results.css"), "utf-8");
    for (const selector of [".rv2-chip", ".rv2-chip-more", ".rv2-band-more", ".rv2-full-action", ".rv2-pick",
      ".rv2-zero-remind-btn", ".rv2-sooner"]) {
      const body = css.match(new RegExp(`\\n\\${selector}\\s*{([^}]*)}`))?.[1] ?? "";
      const rem = Number(body.match(/min-height:\s*([\d.]+)rem/)?.[1] ?? 0);
      expect(rem * 16, `${selector} min-height`).toBeGreaterThanOrEqual(44);
    }
  });
});
