import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "../hooks/useAuth";
import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Mocks — vi.mock factories are hoisted, so no outer variable refs
// ---------------------------------------------------------------------------

vi.mock("posthog-js", () => ({
  default: {
    identify: vi.fn(),
    reset: vi.fn(),
    capture: vi.fn(),
  },
}));

vi.mock("../api", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  updateProfile: vi.fn(),
  track: vi.fn(),
}));

import { getMe, login, signup, logout, updateProfile, track } from "../api";
import posthog from "posthog-js";

const mockGetMe = vi.mocked(getMe);
const mockLogin = vi.mocked(login);
const mockSignup = vi.mocked(signup);
const mockLogout = vi.mocked(logout);
const mockUpdateProfile = vi.mocked(updateProfile);
const mockTrack = vi.mocked(track);
const mockPosthog = vi.mocked(posthog);

const TEST_USER = {
  id: 1,
  email: "test@example.com",
  display_name: "Tester",
  home_base: "Seattle, WA",
  default_state: "WA",
  default_nights: 2,
  default_from: "Seattle, WA",
  recommendations_enabled: true,
  preferred_tags: ["lakeside"],
  onboarding_complete: true,
};

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetMe.mockRejectedValue(new Error("no session"));
  });

  test("loads user on mount when session exists", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toEqual(TEST_USER);
    expect(mockGetMe).toHaveBeenCalledOnce();
  });

  test("handles no session (getMe throws)", async () => {
    mockGetMe.mockRejectedValue(new Error("401"));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  test("login sets user and identifies with posthog", async () => {
    mockLogin.mockResolvedValue(TEST_USER as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login("test@example.com", "password123");
    });

    expect(result.current.user).toEqual(TEST_USER);
    expect(mockLogin).toHaveBeenCalledWith("test@example.com", "password123");
    expect(mockTrack).toHaveBeenCalledWith("login", {});

    await waitFor(() => {
      expect(mockPosthog.identify).toHaveBeenCalledWith(String(TEST_USER.id), {
        display_name: TEST_USER.display_name,
      });
    });
  });

  test("signup sets user and identifies with posthog", async () => {
    mockSignup.mockResolvedValue(TEST_USER as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.signup("test@example.com", "password123", "Tester");
    });

    expect(result.current.user).toEqual(TEST_USER);
    expect(mockSignup).toHaveBeenCalledWith("test@example.com", "password123", "Tester");
    expect(mockTrack).toHaveBeenCalledWith("signup", {});
  });

  test("logout clears user and resets posthog", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);
    mockLogout.mockResolvedValue(undefined as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(mockLogout).toHaveBeenCalledOnce();

    await waitFor(() => {
      expect(mockPosthog.reset).toHaveBeenCalled();
    });
  });

  test("updateProfile updates user state", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);
    const updated = { ...TEST_USER, display_name: "Updated" };
    mockUpdateProfile.mockResolvedValue(updated as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));

    await act(async () => {
      await result.current.updateProfile({ display_name: "Updated" });
    });

    expect(result.current.user).toEqual(updated);
  });

  test("throws when used outside AuthProvider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within AuthProvider",
    );
    spy.mockRestore();
  });
});
