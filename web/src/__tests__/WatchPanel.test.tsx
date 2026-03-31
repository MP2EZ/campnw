import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "test@example.com", display_name: "Tester" },
  }),
}));

vi.mock("../hooks/usePushNotifications", () => ({
  usePushNotifications: () => ({ subscribed: true, subscribe: vi.fn() }),
}));

vi.mock("../components/PollDashboard", () => ({
  PollDashboard: () => <div data-testid="poll-dashboard" />,
}));

vi.mock("../components/ShareButton", () => ({
  ShareButton: () => <button>Share</button>,
}));

vi.mock("../api", () => ({
  getWatches: vi.fn().mockResolvedValue([]),
  deleteWatch: vi.fn().mockResolvedValue(undefined),
  toggleWatch: vi.fn().mockResolvedValue({ enabled: false }),
  createWatch: vi.fn().mockResolvedValue({ id: 1 }),
  track: vi.fn(),
}));

import { WatchPanel, WatchButton } from "../components/WatchPanel";
import { getWatches, deleteWatch, toggleWatch, createWatch } from "../api";
import type { WatchData } from "../api";

const MOCK_WATCH: WatchData = {
  id: 1,
  facility_id: "232465",
  name: "Ohanapecosh",
  start_date: "2026-06-01",
  end_date: "2026-06-30",
  min_nights: 2,
  days_of_week: [4, 5, 6],
  notify_topic: "",
  enabled: true,
  created_at: "2026-03-22T10:00:00Z",
};

const TEMPLATE_WATCH: WatchData = {
  ...MOCK_WATCH,
  id: 2,
  name: "WA Lakeside",
  watch_type: "template",
};

// ---------------------------------------------------------------------------
// WatchPanel
// ---------------------------------------------------------------------------

describe("WatchPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns null when closed", () => {
    const { container } = render(<WatchPanel open={false} onClose={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  test("renders dialog with title when open", async () => {
    vi.mocked(getWatches).mockResolvedValue([]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
  });

  test("shows empty state when no watches", async () => {
    vi.mocked(getWatches).mockResolvedValue([]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("No active watches.")).toBeInTheDocument();
    });
  });

  test("renders watch items with name and dates", async () => {
    vi.mocked(getWatches).mockResolvedValue([MOCK_WATCH]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Ohanapecosh")).toBeInTheDocument();
      expect(screen.getByText(/2026-06-01 → 2026-06-30/)).toBeInTheDocument();
    });
  });

  test("renders days of week for watch", async () => {
    vi.mocked(getWatches).mockResolvedValue([MOCK_WATCH]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Fri, Sat, Sun")).toBeInTheDocument();
    });
  });

  test("shows template badge for template watches", async () => {
    vi.mocked(getWatches).mockResolvedValue([TEMPLATE_WATCH]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Search pattern")).toBeInTheDocument();
    });
  });

  test("delete button removes watch", async () => {
    vi.mocked(getWatches).mockResolvedValue([MOCK_WATCH]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => screen.getByText("Ohanapecosh"));

    fireEvent.click(screen.getByLabelText("Delete watch for Ohanapecosh"));

    await waitFor(() => {
      expect(vi.mocked(deleteWatch)).toHaveBeenCalledWith(1);
    });
  });

  test("toggle button pauses watch", async () => {
    vi.mocked(getWatches).mockResolvedValue([MOCK_WATCH]);
    vi.mocked(toggleWatch).mockResolvedValue({ enabled: false });
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => screen.getByText("Ohanapecosh"));

    fireEvent.click(screen.getByLabelText("Pause watch for Ohanapecosh"));

    await waitFor(() => {
      expect(vi.mocked(toggleWatch)).toHaveBeenCalledWith(1);
      expect(screen.getByText("Paused")).toBeInTheDocument();
    });
  });

  test("Escape key calls onClose", async () => {
    vi.mocked(getWatches).mockResolvedValue([]);
    const onClose = vi.fn();
    render(<WatchPanel open={true} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  test("close button calls onClose", async () => {
    vi.mocked(getWatches).mockResolvedValue([]);
    const onClose = vi.fn();
    render(<WatchPanel open={true} onClose={onClose} />);

    fireEvent.click(screen.getByLabelText("Close watchlist"));
    expect(onClose).toHaveBeenCalled();
  });

  test("shows error state", async () => {
    vi.mocked(getWatches).mockRejectedValue(new Error("Network error"));
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  test("renders PollDashboard for authenticated users", async () => {
    vi.mocked(getWatches).mockResolvedValue([]);
    render(<WatchPanel open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("poll-dashboard")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// WatchButton
// ---------------------------------------------------------------------------

describe("WatchButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders Watch button", () => {
    render(
      <WatchButton
        facilityId="232465"
        name="Ohanapecosh"
        startDate="2026-06-01"
        endDate="2026-06-30"
      />,
    );
    expect(screen.getByText("Watch")).toBeInTheDocument();
  });

  test("creates watch on click and shows Watching", async () => {
    vi.mocked(createWatch).mockResolvedValue({ id: 1 } as any);
    render(
      <WatchButton
        facilityId="232465"
        name="Ohanapecosh"
        startDate="2026-06-01"
        endDate="2026-06-30"
      />,
    );

    fireEvent.click(screen.getByText("Watch"));

    await waitFor(() => {
      expect(vi.mocked(createWatch)).toHaveBeenCalledWith(
        expect.objectContaining({
          facility_id: "232465",
          start_date: "2026-06-01",
          end_date: "2026-06-30",
        }),
      );
      expect(screen.getByText("Watching")).toBeInTheDocument();
    });
  });

  test("calls onCreated callback after watch creation", async () => {
    vi.mocked(createWatch).mockResolvedValue({ id: 1 } as any);
    const onCreated = vi.fn();
    render(
      <WatchButton
        facilityId="232465"
        name="Ohanapecosh"
        startDate="2026-06-01"
        endDate="2026-06-30"
        onCreated={onCreated}
      />,
    );

    fireEvent.click(screen.getByText("Watch"));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledOnce();
    });
  });
});
