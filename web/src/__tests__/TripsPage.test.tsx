import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

/**
 * Deleting a trip is irreversible, has no undo, and its button sits ~22px tall
 * immediately beside the full-row link — so a mis-tap destroyed data. It also
 * had no try/catch while removing the row optimistically, meaning a failed
 * request left the user believing the delete had succeeded.
 */

const mockDeleteTrip = vi.fn();
const mockGetTrips = vi.fn();

vi.mock("../api", () => ({
  getTrips: (...a: unknown[]) => mockGetTrips(...a),
  createTrip: vi.fn(),
  deleteTrip: (...a: unknown[]) => mockDeleteTrip(...a),
  track: vi.fn(),
}));

// Stable identity: the fetch effect keys on `user`, so returning a fresh
// object literal each render would refetch (and reset state) continuously.
const AUTH = { user: { id: 1, email: "a@b.c" }, loading: false };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => AUTH }));

import TripsPage from "../pages/TripsPage";

const TRIP = {
  id: 7,
  name: "Rainier Weekend",
  start_date: "2026-06-05",
  end_date: "2026-06-07",
  campground_count: 2,
};

function renderPage() {
  return render(
    <HelmetProvider>
      <MemoryRouter>
        <TripsPage />
      </MemoryRouter>
    </HelmetProvider>,
  );
}

describe("TripsPage destructive delete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTrips.mockResolvedValue([TRIP]);
    mockDeleteTrip.mockResolvedValue(undefined);
  });

  test("first click asks for confirmation instead of deleting", async () => {
    renderPage();
    await screen.findByText("Rainier Weekend");

    fireEvent.click(
      screen.getByRole("button", { name: /^Delete Rainier Weekend$/i }),
    );

    expect(mockDeleteTrip).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /Confirm delete Rainier Weekend/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancel delete/i })).toBeInTheDocument();
  });

  test("confirming deletes and removes the row", async () => {
    renderPage();
    await screen.findByText("Rainier Weekend");

    fireEvent.click(screen.getByRole("button", { name: /^Delete Rainier Weekend$/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm delete Rainier Weekend/i }),
    );

    await waitFor(() => expect(mockDeleteTrip).toHaveBeenCalledWith(7));
    await waitFor(() =>
      expect(screen.queryByText("Rainier Weekend")).not.toBeInTheDocument(),
    );
  });

  test("cancelling leaves the trip alone", async () => {
    renderPage();
    await screen.findByText("Rainier Weekend");

    fireEvent.click(screen.getByRole("button", { name: /^Delete Rainier Weekend$/i }));
    fireEvent.click(screen.getByRole("button", { name: /Cancel delete/i }));

    expect(mockDeleteTrip).not.toHaveBeenCalled();
    expect(screen.getByText("Rainier Weekend")).toBeInTheDocument();
  });

  test("a failed delete surfaces an error and keeps the row", async () => {
    mockDeleteTrip.mockRejectedValue(new Error("network"));
    renderPage();
    await screen.findByText("Rainier Weekend");

    fireEvent.click(screen.getByRole("button", { name: /^Delete Rainier Weekend$/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm delete Rainier Weekend/i }),
    );

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    // The row must still be there — previously it was removed optimistically
    // with no catch, so the user was told a delete succeeded that had not.
    expect(screen.getByText("Rainier Weekend")).toBeInTheDocument();
  });
});
