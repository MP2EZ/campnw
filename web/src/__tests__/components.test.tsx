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
// Hero photo / postcard placeholder (v1.35)
// ---------------------------------------------------------------------------

const PHOTO_RESULT = {
  ...MOCK_RESULT,
  image_urls: [
    "https://cdn.recreation.gov/a.webp",
    "https://cdn.recreation.gov/b.webp",
    "https://cdn.recreation.gov/c.webp",
  ],
  image_attribution: "Recreation.gov",
  state: "WA",
} as any;

const NO_PHOTO_RESULT = {
  ...MOCK_RESULT,
  facility_id: "WA-1",
  name: "Deception Pass",
  booking_system: "wa_state",
  state: "WA",
  image_urls: [],
  image_attribution: "",
} as any;

describe("ResultCard photos", () => {
  beforeEach(() => vi.clearAllMocks());

  test("does not render hero photo or placeholder when collapsed", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByTestId("postcard-placeholder")).not.toBeInTheDocument();
  });

  test("renders HeroPhoto with lazy-loaded img + alt + security attrs when expanded", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("decoding", "async");
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(img).toHaveAttribute("width", "600");
    expect(img).toHaveAttribute("height", "338");
    expect(img).toHaveAttribute("src", "https://cdn.recreation.gov/a.webp");
    // v1.35 audit W1: alt now "Photo of {name}" — name carried by the
    // card header above; tag was producing odd "Tinkham comma campfire" speech.
    expect(img.alt).toBe("Photo of Ohanapecosh");
  });

  test("attribution renders without requiring hover (WCAG 1.4.13)", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));
    const attribution = screen.getByText("Photo: Recreation.gov");
    expect(attribution).toBeInTheDocument();
    // Must be visible by default (no inline opacity: 0)
    expect(attribution.style.opacity).not.toBe("0");
  });

  test("dot pager uses role=group + aria-current (not tablist)", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    // v1.35 audit S1/B1: was role=tab/tablist + aria-selected. Now
    // plain buttons inside role=group with aria-current on active.
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    const pager = screen.getByRole("group", { name: /photo 1 of 3/i });
    expect(pager).toBeInTheDocument();

    const dots = screen.getAllByRole("button", {
      name: /show photo \d of 3/i,
    });
    expect(dots).toHaveLength(3);
    expect(dots[0]).toHaveAttribute("aria-current", "true");
    expect(dots[1]).not.toHaveAttribute("aria-current");

    fireEvent.click(dots[1]);
    expect(dots[1]).toHaveAttribute("aria-current", "true");
    expect(dots[0]).not.toHaveAttribute("aria-current");

    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.src).toContain("b.webp");

    expect(track).toHaveBeenCalledWith(
      "card_photo_paged",
      expect.objectContaining({
        facility_id: "232465",
        source: "recgov",
        index: 1,
        total: 3,
        via: "dot",
      }),
    );
  });

  test("aria-live region announces photo change on paging (WCAG 4.1.3)", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    // Initial announcement
    const liveRegion = document.querySelector('[aria-live="polite"]');
    expect(liveRegion?.textContent).toMatch(/Photo 1 of 3/);

    // After paging, text updates
    fireEvent.click(screen.getByRole("button", { name: /next photo/i }));
    expect(liveRegion?.textContent).toMatch(/Photo 2 of 3/);
  });

  test("next arrow advances index and wraps at end", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    const next = screen.getByRole("button", { name: /next photo/i });
    fireEvent.click(next); // 0 -> 1
    fireEvent.click(next); // 1 -> 2
    fireEvent.click(next); // 2 -> 0 (wrap)

    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.src).toContain("a.webp");
    expect(track).toHaveBeenLastCalledWith(
      "card_photo_paged",
      expect.objectContaining({ index: 0, via: "arrow" }),
    );
  });

  test("prev arrow wraps from first to last", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    const prev = screen.getByRole("button", { name: /previous photo/i });
    fireEvent.click(prev); // 0 -> 2 (wrap)

    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.src).toContain("c.webp");
    expect(track).toHaveBeenLastCalledWith(
      "card_photo_paged",
      expect.objectContaining({ index: 2, via: "arrow" }),
    );
  });

  test("renders PostcardPlaceholder with single aria-label and hidden inner content", () => {
    render(<ResultCard result={NO_PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /deception pass/i }));

    const placeholder = screen.getByTestId("postcard-placeholder");
    expect(placeholder).toBeInTheDocument();

    // v1.35 audit S5/B6: aria-label carries name + features so AT speaks
    // once. Inner SVG content is wrapped in aria-hidden=true to prevent
    // double-announce on NVDA+Chrome / VO+Safari.
    const svg = screen.getByRole("img", {
      name: /Deception Pass.*Illustrated placeholder.*Features:/i,
    });
    expect(svg).toBeInTheDocument();
    const innerGroup = svg.querySelector('g[aria-hidden="true"]');
    expect(innerGroup).toBeInTheDocument();

    // No <img> tag for an actual photo
    expect(placeholder.querySelector("img")).toBeNull();
  });

  test("PostcardPlaceholder includes region in subtitle when provided", () => {
    const RECGOV_WITH_REGION = {
      ...MOCK_RESULT,
      facility_id: "232465",
      booking_system: "recgov",
      state: "WA",
      region: "Mt. Rainier NP",
      tags: ["forest"],
      image_urls: [],
    } as any;
    render(<ResultCard result={RECGOV_WITH_REGION} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));

    const svg = screen.getByRole("img", {
      name: /Mt\. Rainier NP, WA/i,
    });
    expect(svg).toBeInTheDocument();
  });

  test("PostcardPlaceholder uses source color from bookingSystem", () => {
    // WA-themed placeholder should paint with the WA teal stripe.
    const { unmount } = render(<ResultCard result={NO_PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /deception pass/i }));
    const waPlaceholder = screen.getByTestId("postcard-placeholder");
    const waStripe = waPlaceholder.querySelector('rect[height="6"]');
    expect(waStripe).toHaveAttribute("fill", "#1a8a7a");
    unmount();

    // Same placeholder for a recgov campground (no photos) should use Rec.gov green.
    const RECGOV_NO_PHOTO = {
      ...NO_PHOTO_RESULT,
      facility_id: "recgov-1",
      name: "No Photo Camp",
      booking_system: "recgov",
    } as any;
    render(<ResultCard result={RECGOV_NO_PHOTO} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /no photo camp/i }));
    const recgovPlaceholder = screen.getByTestId("postcard-placeholder");
    const recgovStripe = recgovPlaceholder.querySelector('rect[height="6"]');
    expect(recgovStripe).toHaveAttribute("fill", "#5a8a32");
  });

  test("card_expand event includes has_photo flag", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));
    expect(track).toHaveBeenCalledWith(
      "card_expand",
      expect.objectContaining({ has_photo: 1 }),
    );
  });

  test("card_expand has_photo is 0 when no image_urls", () => {
    render(<ResultCard result={NO_PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /deception pass/i }));
    expect(track).toHaveBeenCalledWith(
      "card_expand",
      expect.objectContaining({ has_photo: 0 }),
    );
  });

  test("img onError fires photo_load_failed once per url + truncates query", () => {
    // v1.35 audit R6: URL is query-stripped + truncated to 200 chars before
    // sending to PostHog — forward-safe in case RIDB ever signs URLs.
    const TOKENIZED = {
      ...PHOTO_RESULT,
      image_urls: [
        "https://cdn.recreation.gov/a.webp?token=secret_value&exp=123",
      ],
    } as any;
    render(<ResultCard result={TOKENIZED} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));
    const img = screen.getByRole("img") as HTMLImageElement;

    fireEvent.error(img);
    fireEvent.error(img); // dedupe — same url, no second event

    const calls = (track as ReturnType<typeof vi.fn>).mock.calls
      .filter((c) => c[0] === "photo_load_failed");
    expect(calls).toHaveLength(1);
    expect(calls[0][1].url).toBe("https://cdn.recreation.gov/a.webp");
    expect(calls[0][1].url).not.toContain("token");
    expect(calls[0][1]).toMatchObject({
      facility_id: "232465",
      source: "recgov",
      index: 0,
    });
  });

  test("book_click includes has_photo property", () => {
    render(<ResultCard result={PHOTO_RESULT} view="dates" />);
    fireEvent.click(screen.getByRole("button", { name: /ohanapecosh/i }));
    fireEvent.click(screen.getByText(/View on Recreation\.gov/i));
    expect(track).toHaveBeenCalledWith(
      "book_click",
      expect.objectContaining({
        facility_id: "232465",
        type: "view_page",
        has_photo: 1,
      }),
    );
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

// ---------------------------------------------------------------------------
// Regression: collapsed cards must not build their body DOM (audit PERF-08)
// ---------------------------------------------------------------------------

describe("ResultCard collapsed body", () => {
  const MANY_WINDOWS = {
    ...MOCK_RESULT,
    windows: Array.from({ length: 60 }, (_, i) => ({
      campsite_id: `c${i}`,
      site_name: `Site ${i}`,
      loop: "Loop A",
      campsite_type: "tent",
      start_date: "2026-06-05",
      end_date: "2026-06-07",
      nights: 2,
      max_people: 4,
      is_fcfs: false,
      booking_url: `https://example.com/book/${i}`,
    })),
  };

  // .card-body collapses via grid-template-rows: 0fr — the subtree is hidden
  // but still built, laid out and styled. SiteView emits one anchor per window
  // with no cap, so a large result set put tens of thousands of invisible nodes
  // in the document across a 20-card list.
  test("renders no window links while collapsed", () => {
    const { container } = render(
      <ResultCard result={MANY_WINDOWS} view="sites" />
    );
    expect(container.querySelectorAll("a[href^='https://example.com/book/']"))
      .toHaveLength(0);
  });

  test("renders them once expanded", () => {
    const { container } = render(
      <ResultCard result={MANY_WINDOWS} view="sites" />
    );
    fireEvent.click(screen.getByRole("button", { name: /Ohanapecosh/i }));
    expect(
      container.querySelectorAll("a[href^='https://example.com/book/']").length
    ).toBeGreaterThan(0);
  });

  test("body stays mounted after collapsing again, so the transition still runs", () => {
    const { container } = render(
      <ResultCard result={MANY_WINDOWS} view="sites" />
    );
    const toggle = screen.getByRole("button", { name: /Ohanapecosh/i });
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(
      container.querySelectorAll("a[href^='https://example.com/book/']").length
    ).toBeGreaterThan(0);
  });
})
