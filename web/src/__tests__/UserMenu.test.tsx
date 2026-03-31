import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockLogout = vi.fn();
const mockUpdateProfile = vi.fn().mockResolvedValue(undefined);

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: "test@example.com",
      display_name: "Tester",
      home_base: "Seattle, WA",
      default_state: "WA",
      default_nights: 2,
      recommendations_enabled: false,
    },
    logout: mockLogout,
    updateProfile: mockUpdateProfile,
  }),
}));

vi.mock("../api", () => ({
  exportData: vi.fn().mockResolvedValue({ searches: [], watches: [] }),
  deleteAccount: vi.fn().mockResolvedValue(undefined),
}));

import { UserMenu } from "../components/UserMenu";
import { deleteAccount } from "../api";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UserMenu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLogout.mockResolvedValue(undefined);
  });

  test("renders user display name as trigger", () => {
    render(<UserMenu />);
    expect(screen.getByText("Tester")).toBeInTheDocument();
  });

  test("trigger has aria-expanded false when closed", () => {
    render(<UserMenu />);
    expect(screen.getByText("Tester")).toHaveAttribute("aria-expanded", "false");
  });

  test("opens dropdown on click", () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));

    expect(screen.getByText("Tester")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Preferences")).toBeInTheDocument();
    expect(screen.getByText("Export data")).toBeInTheDocument();
    expect(screen.getByText("Delete account")).toBeInTheDocument();
    expect(screen.getByText("Sign out")).toBeInTheDocument();
  });

  test("Sign out calls logout", async () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Sign out"));

    await waitFor(() => {
      expect(mockLogout).toHaveBeenCalledOnce();
    });
  });

  test("Delete account shows confirmation, then deletes", async () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Delete account"));

    // Confirmation UI
    expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() => {
      expect(vi.mocked(deleteAccount)).toHaveBeenCalledOnce();
      expect(mockLogout).toHaveBeenCalledOnce();
    });
  });

  test("Delete account cancel returns to main menu", () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Delete account"));
    fireEvent.click(screen.getByText("Cancel"));

    // Back to main menu
    expect(screen.getByText("Preferences")).toBeInTheDocument();
  });

  test("Preferences shows form with user values", () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Preferences"));

    expect(screen.getByDisplayValue("Tester")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Seattle, WA")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  test("Preferences cancel returns to main menu", () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Preferences"));
    fireEvent.click(screen.getByText("Cancel"));

    expect(screen.getByText("Preferences")).toBeInTheDocument();
  });

  test("Preferences save calls updateProfile", async () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByText("Tester"));
    fireEvent.click(screen.getByText("Preferences"));

    // Change display name
    const nameInput = screen.getByDisplayValue("Tester");
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(mockUpdateProfile).toHaveBeenCalledWith(
        expect.objectContaining({ display_name: "New Name" }),
      );
    });
  });
});
