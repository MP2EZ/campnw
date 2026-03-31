import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks — must come before component imports
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  track: vi.fn(),
  compareCampgrounds: vi.fn(),
}));

vi.mock("../components/WatchPanel", () => ({
  WatchButton: () => <button>Watch</button>,
}));

vi.mock("../components/SaveToTripButton", () => ({
  SaveToTripButton: () => <button>Save to trip</button>,
}));

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "test@example.com", display_name: "Test" },
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    updateProfile: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import { ResultCard } from "../components/ResultCard";
import { CompareBar } from "../components/CompareBar";
import { OnboardingModal } from "../components/OnboardingModal";
import { compareCampgrounds, track } from "../api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_RESULT = {
  facility_id: "232465",
  name: "Ohanapecosh",
  booking_system: "recgov",
  total_available_sites: 5,
  fcfs_sites: 0,
  windows: [],
  availability_url: "https://recreation.gov/camping/campgrounds/232465",
  estimated_drive_minutes: 150,
  tags: ["forest", "riverside", "trails", "swimming", "fishing"],
  elevator_pitch: "Old-growth forest camping",
  vibe: "Peaceful and shaded",
  description_rewrite: null,
  best_for: "families",
  latitude: 46.75,
  longitude: -121.8,
  error: null,
} as any;

const ERROR_RESULT = {
  ...MOCK_RESULT,
  facility_id: "999999",
  name: "Broken Camp",
  error: "Facility returned 404",
  total_available_sites: 0,
  windows: [],
} as any;

// ---------------------------------------------------------------------------
// ResultCard
// ---------------------------------------------------------------------------

describe("ResultCard", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders campground name and source badge", () => {
    render(<ResultCard result={MOCK_RESULT} view="dates" />);
    expect(screen.getByText("Ohanapecosh")).toBeInTheDocument();
    expect(screen.getByText("Rec.gov")).toBeInTheDocument();
  });

  test("renders drive time badge", () => {
    render(<ResultCard result={MOCK_RESULT} view="dates" />);
    expect(screen.getByText("~2h 30m")).toBeInTheDocument();
  });

  test("shows up to 4 tags", () => {
    render(<ResultCard result={MOCK_RESULT} view="dates" />);
    expect(screen.getByText("forest")).toBeInTheDocument();
    expect(screen.getByText("riverside")).toBeInTheDocument();
    expect(screen.getByText("trails")).toBeInTheDocument();
    expect(screen.getByText("swimming")).toBeInTheDocument();
    // 5th tag should not be rendered
    expect(screen.queryByText("fishing")).not.toBeInTheDocument();
  });

  test("click header toggles expanded state", () => {
    render(<ResultCard result={MOCK_RESULT} view="dates" />);
    const header = screen.getByRole("button", { name: /ohanapecosh/i });

    expect(header).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
  });

  test("renders error card for error results", () => {
    render(<ResultCard result={ERROR_RESULT} view="dates" />);
    expect(screen.getByText("Broken Camp")).toBeInTheDocument();
    expect(screen.getByText("Facility returned 404")).toBeInTheDocument();
  });

  test("shows elevator pitch when provided", () => {
    render(<ResultCard result={MOCK_RESULT} view="dates" />);
    expect(screen.getByText("Old-growth forest camping")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// CompareBar
// ---------------------------------------------------------------------------

describe("CompareBar", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns null when no selections", () => {
    const { container } = render(
      <CompareBar selectedIds={new Set()} onClear={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("shows count and Compare button when items selected", () => {
    render(
      <CompareBar
        selectedIds={new Set(["232465", "232466"])}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(screen.getByText("Compare (2)")).toBeInTheDocument();
  });

  test("Compare button disabled with fewer than 2 selections", () => {
    render(
      <CompareBar
        selectedIds={new Set(["232465"])}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByText("Compare (1)")).toBeDisabled();
  });

  test("Clear button calls onClear", () => {
    const onClear = vi.fn();
    render(
      <CompareBar
        selectedIds={new Set(["232465", "232466"])}
        onClear={onClear}
      />,
    );
    fireEvent.click(screen.getByText("Clear"));
    expect(onClear).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// OnboardingModal
// ---------------------------------------------------------------------------

describe("OnboardingModal", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders step 1 with home base input", () => {
    render(<OnboardingModal onClose={vi.fn()} />);
    expect(screen.getByText("Welcome to campable")).toBeInTheDocument();
    expect(screen.getByLabelText("Home base city")).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
  });

  test("Escape key calls onClose", () => {
    const onClose = vi.fn();
    render(<OnboardingModal onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  test("shows tag options in step 2 after clicking Next", async () => {
    render(<OnboardingModal onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Next"));

    await waitFor(() => {
      expect(screen.getByText("Step 2 of 2")).toBeInTheDocument();
    });

    // Should show tag buttons
    expect(screen.getByText("lakeside")).toBeInTheDocument();
    expect(screen.getByText("riverside")).toBeInTheDocument();
    expect(screen.getByText("0/5 selected")).toBeInTheDocument();
  });

  test("tag selection limited to 5", async () => {
    render(<OnboardingModal onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Next"));

    await waitFor(() => {
      expect(screen.getByText("Step 2 of 2")).toBeInTheDocument();
    });

    const tags = ["lakeside", "riverside", "beach", "forest", "alpine"];
    for (const tag of tags) {
      fireEvent.click(screen.getByText(tag));
    }
    expect(screen.getByText("5/5 selected")).toBeInTheDocument();

    // 6th tag should not activate
    fireEvent.click(screen.getByText("remote"));
    expect(screen.getByText("5/5 selected")).toBeInTheDocument();
  });
});
