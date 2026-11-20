import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  track: vi.fn(),
}));

const authMocks = vi.hoisted(() => ({
  signup: vi.fn(),
  resendConfirmation: vi.fn(),
}));

vi.mock("../hooks/useAuth", () => ({
  EMAIL_NOT_CONFIRMED: "Confirm your email first.",
  useAuth: () => ({
    user: { id: 1, email: "test@example.com", display_name: "Test" },
    loading: false,
    login: vi.fn(),
    signup: authMocks.signup,
    resendConfirmation: authMocks.resendConfirmation,
    logout: vi.fn(),
    updateProfile: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import { OnboardingModal } from "../components/OnboardingModal";
import { AuthModal } from "../components/AuthModal";
import { track } from "../api";

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

describe("AuthModal email confirmation", () => {
  beforeEach(() => vi.clearAllMocks());

  function submitSignup(onClose = vi.fn()) {
    render(<AuthModal open entryPoint="header" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Create one" }));
    fireEvent.change(screen.getByTestId("email-input"), {
      target: { value: "new@example.com" },
    });
    fireEvent.change(screen.getByTestId("password-input"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    return onClose;
  }

  test("a sign-up that needs confirmation shows check-your-email and stays open", async () => {
    authMocks.signup.mockResolvedValue({ needsConfirmation: true });
    const onClose = submitSignup();

    expect(await screen.findByTestId("auth-check-email")).toHaveTextContent(
      "new@example.com",
    );
    expect(screen.getByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  test("a sign-up with a session closes the modal", async () => {
    authMocks.signup.mockResolvedValue({ needsConfirmation: false });
    const onClose = submitSignup();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("send it again resends to the pending address", async () => {
    authMocks.signup.mockResolvedValue({ needsConfirmation: true });
    authMocks.resendConfirmation.mockResolvedValue(undefined);
    submitSignup();

    fireEvent.click(await screen.findByRole("button", { name: "Send it again" }));

    await screen.findByText(/Sent\./);
    expect(authMocks.resendConfirmation).toHaveBeenCalledWith("new@example.com");
  });

  test("back to sign in returns to the login form", async () => {
    authMocks.signup.mockResolvedValue({ needsConfirmation: true });
    submitSignup();

    fireEvent.click(await screen.findByRole("button", { name: "Back to sign in" }));

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByTestId("email-input")).toBeInTheDocument();
  });
});
