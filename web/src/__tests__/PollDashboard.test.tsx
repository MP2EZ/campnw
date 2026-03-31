import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  getPollStatus: vi.fn(),
}));

import { PollDashboard } from "../components/PollDashboard";
import { getPollStatus } from "../api";
import type { PollStatus } from "../api";

const MOCK_STATUS: PollStatus = {
  last_poll: new Date(Date.now() - 5 * 60_000).toISOString(), // 5m ago
  next_poll: new Date(Date.now() + 10 * 60_000).toISOString(), // in 10m
  active_watches: 3,
  last_changes: 1,
  last_errors: 0,
  recent_notifications: [],
};

const STATUS_WITH_NOTIFICATIONS: PollStatus = {
  ...MOCK_STATUS,
  recent_notifications: [
    {
      watch_name: "Ohanapecosh",
      channel: "web_push",
      status: "sent",
      changes_count: 2,
      sent_at: new Date(Date.now() - 30 * 60_000).toISOString(),
    },
    {
      watch_name: "Kalaloch",
      channel: "ntfy",
      status: "sent",
      changes_count: 1,
      sent_at: new Date(Date.now() - 120 * 60_000).toISOString(),
    },
  ],
};

const STATUS_WITH_ERRORS: PollStatus = {
  ...MOCK_STATUS,
  last_errors: 2,
};

describe("PollDashboard", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns null when closed", () => {
    const { container } = render(<PollDashboard open={false} />);
    expect(container.innerHTML).toBe("");
  });

  test("shows loading state", () => {
    vi.mocked(getPollStatus).mockReturnValue(new Promise(() => {})); // never resolves
    render(<PollDashboard open={true} />);
    expect(screen.getByText("Loading poll status...")).toBeInTheDocument();
  });

  test("renders poll stats when loaded", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(MOCK_STATUS);
    render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.getByText("Poll status")).toBeInTheDocument();
      expect(screen.getByText("Last poll")).toBeInTheDocument();
      expect(screen.getByText("Next poll")).toBeInTheDocument();
      expect(screen.getByText("Active watches")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  test("shows relative time for last poll", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(MOCK_STATUS);
    render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.getByText("5m ago")).toBeInTheDocument();
    });
  });

  test("shows 'No alerts sent yet' when no notifications", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(MOCK_STATUS);
    render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.getByText("No alerts sent yet.")).toBeInTheDocument();
    });
  });

  test("renders recent notifications", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(STATUS_WITH_NOTIFICATIONS);
    render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.getByText("Recent alerts")).toBeInTheDocument();
      expect(screen.getByText("Ohanapecosh")).toBeInTheDocument();
      expect(screen.getByText("Kalaloch")).toBeInTheDocument();
      expect(screen.getByText(/2 changes/)).toBeInTheDocument();
      expect(screen.getByText(/1 change · ntfy/)).toBeInTheDocument();
    });
  });

  test("shows error count when present", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(STATUS_WITH_ERRORS);
    render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.getByText("Errors")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  test("returns null when API returns null", async () => {
    vi.mocked(getPollStatus).mockResolvedValue(null);
    const { container } = render(<PollDashboard open={true} />);

    await waitFor(() => {
      expect(screen.queryByText("Poll status")).not.toBeInTheDocument();
    });
  });
});
