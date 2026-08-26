import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

/**
 * The privacy page described PostHog as seeing "clicks and page views" while
 * session replay was also enabled, and opt_out_capturing appeared nowhere in
 * the app — the only route out was emailing support.
 */

const { mockPh, mockTrack } = vi.hoisted(() => ({
  mockPh: {
    opt_out_capturing: vi.fn(),
    opt_in_capturing: vi.fn(),
    has_opted_out_capturing: vi.fn(() => false),
  },
  mockTrack: vi.fn(),
}));

vi.mock("../api", () => ({
  getPosthog: () => mockPh,
  track: (...a: unknown[]) => mockTrack(...a),
}));

import { AnalyticsOptOut } from "../components/AnalyticsOptOut";

describe("AnalyticsOptOut", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPh.has_opted_out_capturing.mockReturnValue(false);
  });

  test("opting out calls opt_out_capturing", () => {
    render(<AnalyticsOptOut />);
    fireEvent.click(screen.getByRole("button", { name: /turn analytics off/i }));
    expect(mockPh.opt_out_capturing).toHaveBeenCalled();
  });

  test("the opt-out event fires BEFORE capturing stops", () => {
    // Ordering matters: fired after opt_out_capturing(), the event never
    // leaves the browser and the decision is unmeasurable.
    const order: string[] = [];
    mockTrack.mockImplementation(() => order.push("track"));
    mockPh.opt_out_capturing.mockImplementation(() => order.push("opt_out"));

    render(<AnalyticsOptOut />);
    fireEvent.click(screen.getByRole("button", { name: /turn analytics off/i }));

    expect(order).toEqual(["track", "opt_out"]);
  });

  test("reflects an existing opt-out on mount", () => {
    mockPh.has_opted_out_capturing.mockReturnValue(true);
    render(<AnalyticsOptOut />);
    expect(screen.getByRole("button", { name: /turn analytics back on/i })).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  test("opting back in calls opt_in_capturing", () => {
    mockPh.has_opted_out_capturing.mockReturnValue(true);
    render(<AnalyticsOptOut />);
    fireEvent.click(screen.getByRole("button", { name: /turn analytics back on/i }));
    expect(mockPh.opt_in_capturing).toHaveBeenCalled();
  });

  test("says so when PostHog cannot report a state", () => {
    mockPh.has_opted_out_capturing.mockReturnValue(undefined as unknown as boolean);
    render(<AnalyticsOptOut />);
    expect(screen.getByText(/status unavailable/i)).toBeInTheDocument();
  });
});
