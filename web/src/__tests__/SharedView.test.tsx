import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

/**
 * ShareButton has always copied `${origin}/shared/${uuid}` and the server has
 * always served that payload — but no client route matched it, so recipients
 * got the app shell with an empty content area: no content, no error, no
 * redirect. These cover the states a real recipient hits, including the two
 * the API can return for a dead link (410 revoked/expired, 404 missing).
 */

// vi.hoisted: vi.mock factories are hoisted above const/class declarations,
// so plain top-level bindings are still in their TDZ when the factory runs.
const {
  mockGetSharedLink,
  mockTrack,
  mockSetPersonProperties,
  MockShareUnavailableError,
} = vi.hoisted(() => {
  class Unavailable extends Error {
    readonly kind: string;
    constructor(kind: string) {
      super(kind);
      this.kind = kind;
    }
  }
  return {
    mockGetSharedLink: vi.fn(),
    mockTrack: vi.fn(),
    mockSetPersonProperties: vi.fn(),
    MockShareUnavailableError: Unavailable,
  };
});

vi.mock("../api", () => ({
  getSharedLink: (...a: unknown[]) => mockGetSharedLink(...a),
  track: (...a: unknown[]) => mockTrack(...a),
  getPosthog: () => ({ setPersonProperties: mockSetPersonProperties }),
  ShareUnavailableError: MockShareUnavailableError,
}));

vi.mock("../lib/dates", () => ({
  formatDateRange: (a: string, b: string) => `${a} – ${b}`,
}));

import SharedView from "../pages/SharedView";

function renderAt(uuid = "abc-123") {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[`/shared/${uuid}`]}>
        <Routes>
          <Route path="/shared/:uuid" element={<SharedView />} />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
}

describe("SharedView", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders a shared watch", async () => {
    mockGetSharedLink.mockResolvedValue({
      uuid: "abc-123",
      type: "watch",
      watch: {
        name: "Ohanapecosh",
        facility_id: "232465",
        start_date: "2026-06-01",
        end_date: "2026-06-08",
        min_nights: 2,
      },
    });

    renderAt();
    expect(await screen.findByText("Ohanapecosh")).toBeInTheDocument();
    expect(screen.getByText(/Shared campsite watch/i)).toBeInTheDocument();
    expect(screen.getByText(/2\+ nights/)).toBeInTheDocument();
  });

  test("renders a shared trip and its campgrounds", async () => {
    mockGetSharedLink.mockResolvedValue({
      uuid: "abc-123",
      type: "trip",
      trip: {
        name: "Rainier Loop",
        start_date: "2026-06-01",
        end_date: "2026-06-08",
        campgrounds: [
          { facility_id: "1", source: "recgov", name: "Ohanapecosh" },
          { facility_id: "2", source: "wa_state", name: "Deception Pass" },
        ],
      },
    });

    renderAt();
    expect(await screen.findByText("Rainier Loop")).toBeInTheDocument();
    expect(screen.getByText("Deception Pass")).toBeInTheDocument();
    expect(screen.getByText("WA Parks")).toBeInTheDocument();
  });

  test("a revoked or expired link explains itself", async () => {
    mockGetSharedLink.mockRejectedValue(new MockShareUnavailableError("gone"));
    renderAt();
    expect(await screen.findByText(/revoked.*or it has expired/i)).toBeInTheDocument();
    // Always offer a way forward — a dead link is still a visitor.
    expect(screen.getByRole("link", { name: /search campsites/i })).toBeInTheDocument();
  });

  test("a missing link does not claim it was revoked", async () => {
    mockGetSharedLink.mockRejectedValue(new MockShareUnavailableError("not_found"));
    renderAt();
    expect(await screen.findByText(/couldn't find it/i)).toBeInTheDocument();
  });

  test("a transport error is distinguished from a dead link", async () => {
    mockGetSharedLink.mockRejectedValue(new Error("network"));
    renderAt();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  test("a successful view is attributed to the share loop", async () => {
    mockGetSharedLink.mockResolvedValue({
      uuid: "abc-123",
      type: "trip",
      trip: { name: "T", start_date: "2026-06-01", end_date: "2026-06-02", campgrounds: [] },
    });

    renderAt();
    await waitFor(() =>
      expect(mockTrack).toHaveBeenCalledWith(
        "share_link_landed",
        expect.objectContaining({ share_type: "trip" }),
      ),
    );
    // $set_once, so a later signup is creditable to the share rather than
    // to direct traffic.
    expect(mockSetPersonProperties).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ acquisition_channel: "share" }),
    );
  });

  test("a dead link is not attributed as a share acquisition", async () => {
    mockGetSharedLink.mockRejectedValue(new MockShareUnavailableError("gone"));
    renderAt();
    await screen.findByText(/revoked/i);
    expect(mockSetPersonProperties).not.toHaveBeenCalled();
  });
});
