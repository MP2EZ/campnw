import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks — must come before component imports
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  track: vi.fn(),
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

import { OnboardingModal } from "../components/OnboardingModal";
import { AuthModal } from "../components/AuthModal";
import { track } from "../api";

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
// Auth funnel interiors (audit ANLT-13)
// ---------------------------------------------------------------------------

describe("AuthModal funnel events", () => {
  beforeEach(() => vi.clearAllMocks());

  // The modal had zero track() calls, so the landing -> signup funnel had one
  // step: the success event. No open, no submit attempt, and no failure —
  // the classic silent signup-funnel killer.
  test("opening emits auth_modal_opened with its entry point", () => {
    render(<AuthModal open entryPoint="header" onClose={() => {}} />);
    expect(track).toHaveBeenCalledWith(
      "auth_modal_opened",
      expect.objectContaining({ entry_point: "header", mode: "login" }),
    );
  });

  test("a closed modal emits nothing", () => {
    render(<AuthModal open={false} entryPoint="header" onClose={() => {}} />);
    expect(vi.mocked(track).mock.calls.filter((c) => c[0] === "auth_modal_opened"))
      .toHaveLength(0);
  });

  test("toggling to signup is measurable", () => {
    render(<AuthModal open entryPoint="header" onClose={() => {}} />);
    const toggle = screen.getByRole("button", { name: /create one|sign up/i });
    fireEvent.click(toggle);
    expect(track).toHaveBeenCalledWith(
      "auth_mode_toggled",
      expect.objectContaining({ to: "signup" }),
    );
  });
})
