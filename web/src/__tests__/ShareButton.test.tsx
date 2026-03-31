import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  createShareLink: vi.fn().mockResolvedValue({ uuid: "abc-123-def" }),
  track: vi.fn(),
}));

// Mock clipboard
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

import { ShareButton } from "../components/ShareButton";
import { createShareLink } from "../api";

describe("ShareButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders Share button", () => {
    render(<ShareButton watchId={1} />);
    expect(screen.getByText("Share")).toBeInTheDocument();
    expect(screen.getByTitle("Copy share link")).toBeInTheDocument();
  });

  test("clicking share creates link and copies to clipboard", async () => {
    render(<ShareButton watchId={1} />);
    fireEvent.click(screen.getByText("Share"));

    await waitFor(() => {
      expect(vi.mocked(createShareLink)).toHaveBeenCalledWith({ watch_id: 1, trip_id: undefined });
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining("/shared/abc-123-def"),
      );
      expect(screen.getByText("Link copied")).toBeInTheDocument();
    });
  });

  test("passes trip_id when provided", async () => {
    render(<ShareButton tripId={5} />);
    fireEvent.click(screen.getByText("Share"));

    await waitFor(() => {
      expect(vi.mocked(createShareLink)).toHaveBeenCalledWith({ watch_id: undefined, trip_id: 5 });
    });
  });
});
