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

vi.mock("../api", () => ({
  getTrips: vi.fn().mockResolvedValue([
    { id: 1, name: "Olympic Trip", campgrounds: [] },
    { id: 2, name: "Rainier Weekend", campgrounds: [] },
  ]),
  createTrip: vi.fn().mockResolvedValue({ id: 3, name: "New Trip", campgrounds: [] }),
  addCampgroundToTrip: vi.fn().mockResolvedValue(undefined),
  track: vi.fn(),
}));

import { SaveToTripButton } from "../components/SaveToTripButton";
import { addCampgroundToTrip, createTrip } from "../api";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SaveToTripButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders + Trip button", () => {
    render(<SaveToTripButton facilityId="232465" source="recgov" name="Ohanapecosh" />);
    expect(screen.getByText("+ Trip")).toBeInTheDocument();
  });

  test("button has aria-expanded and aria-haspopup", () => {
    render(<SaveToTripButton facilityId="232465" source="recgov" name="Ohanapecosh" />);
    const btn = screen.getByText("+ Trip");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveAttribute("aria-haspopup", "true");
  });

  test("opens dropdown with existing trips", async () => {
    render(<SaveToTripButton facilityId="232465" source="recgov" name="Ohanapecosh" />);
    fireEvent.click(screen.getByText("+ Trip"));

    await waitFor(() => {
      expect(screen.getByText("Olympic Trip")).toBeInTheDocument();
      expect(screen.getByText("Rainier Weekend")).toBeInTheDocument();
    });
  });

  test("clicking trip saves campground", async () => {
    render(<SaveToTripButton facilityId="232465" source="recgov" name="Ohanapecosh" />);
    fireEvent.click(screen.getByText("+ Trip"));

    await waitFor(() => screen.getByText("Olympic Trip"));
    fireEvent.click(screen.getByText("Olympic Trip"));

    await waitFor(() => {
      expect(vi.mocked(addCampgroundToTrip)).toHaveBeenCalledWith(
        1, "232465", "recgov", "Ohanapecosh",
      );
    });
  });

  test("create new trip input and button", async () => {
    render(<SaveToTripButton facilityId="232465" source="recgov" name="Ohanapecosh" />);
    fireEvent.click(screen.getByText("+ Trip"));

    await waitFor(() => screen.getByPlaceholderText("New trip..."));

    const input = screen.getByPlaceholderText("New trip...");
    fireEvent.change(input, { target: { value: "Summer Camping" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(vi.mocked(createTrip)).toHaveBeenCalledWith("Summer Camping");
    });
  });
});
