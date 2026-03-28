import { describe, test, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import App from "../App";

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
