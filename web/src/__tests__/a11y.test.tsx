import { describe, test, expect, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import App from "../App";
import ResultsPage from "../results/ResultsPage";
import SearchBar from "../results/SearchBar";
import { UI_STORAGE_KEY } from "../results/uiVersion";
import { SearchContext, type SearchContextValue } from "../contexts/SearchContext";
import type { CampgroundResult, Window } from "../api";
import { CampgroundCard } from "../results/CampgroundCard";
import { createSelectionStore, SelectionContext } from "../results/selection";

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

// The split layout's map, without Leaflet (ResultsMap.test covers the real one).
vi.mock("../results/ResultsMap", () => ({ default: () => <div data-testid="results-map" /> }));

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

  test("on desktop the map is a labelled region beside the list, and passes axe", async () => {
    const matchMedia = window.matchMedia;
    window.matchMedia = ((q: string) => ({ ...matchMedia(q), matches: q.includes("min-width: 1024px") })) as typeof matchMedia;
    try {
      const { container } = renderV2();
      const aside = screen.getByRole("complementary", { name: "Map of results" });
      expect(aside).toHaveTextContent("The list has the same places.");
      expect(await within(aside).findByTestId("results-map")).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
    } finally {
      window.matchMedia = matchMedia;
    }
  });

  test("hovering or focusing a card selects it for the map; a pin's card is marked", () => {
    const store = createSelectionStore();
    const { container } = render(
      <SelectionContext.Provider value={store}>
        <CampgroundCard result={v2Place("1", "Dash Point State Park", 48)} params={null} rank={0} />
      </SelectionContext.Provider>,
    );
    const card = container.querySelector("article")!;
    fireEvent.mouseEnter(card);
    expect(store.get()).toEqual({ id: "1", from: "list" });
    fireEvent.mouseLeave(card);
    expect(store.get().id).toBeNull();
    fireEvent.focus(within(card).getAllByRole("link")[0]);
    expect(store.get()).toEqual({ id: "1", from: "list" });
    expect(card).not.toHaveClass("is-selected");
    act(() => store.select("1", "map"));
    expect(card).toHaveClass("is-selected");
  });
});

// ── v2 search bar (v1.48 P3a) ────────────────────────────────────────

function renderBar() {
  const ctx: SearchContextValue = {
    results: null, loading: false, searchDates: null, sourceFilter: new Set(), filteredResults: [],
    searchParams: { start_date: "2027-06-01", end_date: "2027-06-30", nights: 2, days_of_week: "4,5,6",
      from_location: "seattle", max_drive: 180, people: 2, equipment: "tent" },
  };
  return render(
    <SearchContext.Provider value={ctx}>
      <SearchBar onSearch={() => {}} onAsk={() => {}} />
    </SearchContext.Provider>,
  );
}

/** min-height (or height) in px from every rule whose selector list names `selector`. */
function minTarget(css: string, selector: string): number {
  let best = 0;
  for (const [, sel, body] of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (!sel.split(",").some((s) => s.trim() === selector)) continue;
    for (const [, n, unit] of body.matchAll(/(?:^|[\s;])(?:min-)?height:\s*([\d.]+)(px|rem)/g)) {
      best = Math.max(best, Number(n) * (unit === "rem" ? 16 : 1));
    }
  }
  return best;
}

describe("Accessibility: v2 search bar", () => {
  test("the bar, each popover and the typeahead pass axe", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue({ ok: true, json: async () => [
      { facility_id: "1", name: "Ohanapecosh", state: "WA", region: "", booking_system: "recgov", drive_minutes_from_base: 140 },
    ] });
    const { container } = renderBar();
    expect(await axe(container)).toHaveNoViolations();
    const bar = screen.getByRole("search", { name: "Campsite search" });
    for (const name of [/^When/, /^Who/, /^Drive/, /^Where/]) {
      await user.click(within(bar).getByRole("button", { name }));
      expect(await axe(container)).toHaveNoViolations();
    }
    const box = screen.getByRole("combobox", { name: "Or a campground by name" });
    await user.type(box, "oha");
    await waitFor(() => expect(box).toHaveAttribute("aria-expanded", "true"));
    await user.keyboard("{ArrowDown}");
    expect(await axe(container)).toHaveNoViolations();
  });

  test("the mobile sheet passes axe", async () => {
    const user = userEvent.setup();
    const { container } = renderBar();
    await user.click(screen.getByRole("button", { name: /^Edit search/ }));
    expect(screen.getByRole("dialog", { name: "Edit search" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  test("search bar targets are at least 44px", () => {
    const css = readFileSync(join(__dirname, "../results/searchBar.css"), "utf-8");
    for (const selector of [".sb-seg-btn", ".sb-submit", ".sb-chip", ".sb-done", ".sb-go", ".sb-step", ".sb-link",
      ".sb-select", ".sb-input", ".sb-option", ".sb-ask-input", ".sb-ask-go", ".sb-compact-btn"]) {
      expect(minTarget(css, selector), `${selector} height`).toBeGreaterThanOrEqual(44);
    }
  });
});

describe("v2 search bar switch", () => {
  test("v2 replaces the v1 form, NL bar and first-visit state", async () => {
    localStorage.setItem(UI_STORAGE_KEY, "v2");
    try {
      renderRoute("/");
      expect(await screen.findByRole("search", { name: "Campsite search" })).toBeInTheDocument();
      expect(screen.queryByRole("textbox", { name: "Search in plain language" })).toBeNull();
      expect(screen.queryByText("Find your next campsite")).toBeNull();
      expect(screen.getByRole("textbox", { name: "Or ask" })).toBeInTheDocument();
    } finally {
      localStorage.removeItem(UI_STORAGE_KEY);
    }
  });

  test("v1 is unchanged", () => {
    renderRoute("/");
    expect(screen.getByRole("textbox", { name: "Search in plain language" })).toBeInTheDocument();
    expect(screen.getByText("Find your next campsite")).toBeInTheDocument();
    expect(screen.queryByRole("search", { name: "Campsite search" })).toBeNull();
  });
});
