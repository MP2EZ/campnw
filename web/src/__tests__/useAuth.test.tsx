import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const mockSignInWithPassword = vi.fn();
const mockSignUp = vi.fn();
const mockResend = vi.fn();
const mockSignOut = vi.fn();
const mockOnAuthStateChange = vi.fn();

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      signInWithPassword: (...args: unknown[]) => mockSignInWithPassword(...args),
      signUp: (...args: unknown[]) => mockSignUp(...args),
      resend: (...args: unknown[]) => mockResend(...args),
      signOut: (...args: unknown[]) => mockSignOut(...args),
      onAuthStateChange: (...args: unknown[]) => mockOnAuthStateChange(...args),
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    },
  },
}));

// The app talks to the PostHog instance the index.html snippet puts on
// `window` — never to the npm module singleton, which is never init()ed and
// whose methods silently no-op. Mocking `getPosthog` (rather than
// "posthog-js") is what makes these assertions mean anything.
// vi.hoisted, not a plain const: vi.mock factories are hoisted above const
// declarations, so a bare const would still be in its TDZ when the factory runs.
const mockPosthog = vi.hoisted(() => ({
  identify: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("../api", () => ({
  getMe: vi.fn(),
  updateProfile: vi.fn(),
  track: vi.fn(),
  getPosthog: vi.fn(() => mockPosthog),
  unsubscribePush: vi.fn().mockResolvedValue(undefined),
}));

import { AuthProvider, EMAIL_NOT_CONFIRMED, useAuth } from "../hooks/useAuth";
import { getMe, updateProfile, track, unsubscribePush } from "../api";

const mockGetMe = vi.mocked(getMe);
const mockUpdateProfile = vi.mocked(updateProfile);
const mockTrack = vi.mocked(track);

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

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

/** Simulate Supabase calling the onAuthStateChange callback */
function triggerAuthChange(session: unknown) {
  const callback = mockOnAuthStateChange.mock.calls[0]?.[0];
  if (callback) callback("SIGNED_IN", session);
}

describe("useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetMe.mockResolvedValue(null);
    mockOnAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: vi.fn() } },
    });
    mockSignInWithPassword.mockResolvedValue({ error: null });
    mockSignUp.mockResolvedValue({ data: { user: {}, session: null }, error: null });
    mockResend.mockResolvedValue({ error: null });
    mockSignOut.mockResolvedValue({ error: null });
  });

  test("loading becomes false after initialization", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  test("loads user when auth state changes with session", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      triggerAuthChange({ access_token: "test-token" });
    });

    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));
    expect(mockGetMe).toHaveBeenCalled();
  });

  test("login calls supabase signInWithPassword and tracks event", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login("test@example.com", "password123");
    });

    expect(mockSignInWithPassword).toHaveBeenCalledWith({
      email: "test@example.com",
      password: "password123",
    });
    expect(mockTrack).toHaveBeenCalledWith(
      "login",
      expect.objectContaining({ method: "password" }),
    );
  });

  test("login throws on supabase error", async () => {
    mockSignInWithPassword.mockResolvedValue({
      error: { message: "Invalid credentials" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login("test@example.com", "wrong");
      })
    ).rejects.toThrow("Invalid credentials");
  });

  test("signup calls supabase signUp with user metadata", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.signup("test@example.com", "password123", "Tester");
    });

    expect(mockSignUp).toHaveBeenCalledWith({
      email: "test@example.com",
      password: "password123",
      options: {
        data: { display_name: "Tester" },
        emailRedirectTo: `${window.location.origin}/`,
      },
    });
    expect(mockTrack).toHaveBeenCalledWith(
      "signup",
      expect.objectContaining({ method: "password", has_display_name: 1 }),
    );
  });

  // Regression guard: identify() previously ran against the npm posthog-js
  // singleton, which is never init()ed, so it silently no-op'd and every event
  // stayed anonymous. Nothing asserted the call, so the breakage was invisible.
  test("identifies the user against the initialized posthog instance", async () => {
    mockPosthog.identify.mockClear();
    mockGetMe.mockResolvedValue(TEST_USER);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      triggerAuthChange({ access_token: "test-token" });
    });
    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));

    expect(mockPosthog.identify).toHaveBeenCalledWith(
      String(TEST_USER.id),
      expect.objectContaining({ display_name: TEST_USER.display_name }),
    );
  });

  test("logout calls supabase signOut and resets posthog", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      triggerAuthChange({ access_token: "test-token" });
    });
    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(mockSignOut).toHaveBeenCalledOnce();
    await waitFor(() => {
      expect(mockPosthog.reset).toHaveBeenCalled();
    });
  });

  test("logout unregisters this device's push and clears the planner transcript", async () => {
    // SEC-06 / SEC-11: on a shared device the next person must not get the
    // previous user's alerts or see their planner conversation.
    mockGetMe.mockResolvedValue(TEST_USER as any);
    const sub = { endpoint: "https://fcm.googleapis.com/fcm/send/abc", unsubscribe: vi.fn().mockResolvedValue(true) };
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { getRegistration: vi.fn().mockResolvedValue({ pushManager: { getSubscription: () => Promise.resolve(sub) } }) },
    });
    for (const k of ["campable-push-subscribed", "campable-plan-messages",
      "campable-plan-api-messages", "campable-plan-conversation", "campable-theme"]) {
      localStorage.setItem(k, "x");
    }

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      triggerAuthChange({ access_token: "test-token" });
    });
    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));
    await act(async () => {
      await result.current.logout();
    });

    expect(vi.mocked(unsubscribePush)).toHaveBeenCalledWith(sub.endpoint);
    // While the auth header is still valid: the server scopes the delete to the user.
    expect(vi.mocked(unsubscribePush).mock.invocationCallOrder[0])
      .toBeLessThan(mockSignOut.mock.invocationCallOrder[0]);
    expect(sub.unsubscribe).toHaveBeenCalled();
    for (const k of ["campable-push-subscribed", "campable-plan-messages",
      "campable-plan-api-messages", "campable-plan-conversation"]) {
      expect(localStorage.getItem(k)).toBeNull();
    }
    expect(localStorage.getItem("campable-theme")).toBe("x");
    // @ts-expect-error -- test cleanup of the stub
    delete navigator.serviceWorker;
  });

  test("updateProfile updates user state", async () => {
    mockGetMe.mockResolvedValue(TEST_USER as any);
    const updated = { ...TEST_USER, display_name: "Updated" };
    mockUpdateProfile.mockResolvedValue(updated as any);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      triggerAuthChange({ access_token: "test-token" });
    });
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

  test("persisted session triggers getMe() on mount without waiting for onAuthStateChange", async () => {
    // Regression for production bug: supabase-js v2's INITIAL_SESSION
    // event can race React effect registration — if the listener
    // registers after the SDK has already emitted, returning users get
    // stuck on "Loading…" forever because getMe() is never called.
    //
    // The fix explicitly reads the persisted session via getSession() on
    // mount, separately from registering the listener. This test holds
    // that contract: a session in localStorage MUST result in getMe()
    // being called even if onAuthStateChange never fires.
    const { supabase } = await import("../lib/supabase");
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { access_token: "persisted-token" } as never },
      error: null,
    });
    // Listener registered but never invoked — simulates the race
    mockGetMe.mockResolvedValue(TEST_USER as never);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.user).toEqual(TEST_USER));
    expect(mockGetMe).toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  test("signup reports needsConfirmation when Supabase returns no session", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let outcome: { needsConfirmation: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.signup("test@example.com", "password123");
    });

    expect(outcome).toEqual({ needsConfirmation: true });
    expect(mockTrack).toHaveBeenCalledWith(
      "signup",
      expect.objectContaining({ needs_confirmation: 1 }),
    );
  });

  test("signup does not need confirmation when Supabase returns a session", async () => {
    mockSignUp.mockResolvedValue({
      data: { user: {}, session: { access_token: "t" } },
      error: null,
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let outcome: { needsConfirmation: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.signup("test@example.com", "password123");
    });

    expect(outcome).toEqual({ needsConfirmation: false });
  });

  test("login with an unconfirmed email throws a plain explanation", async () => {
    mockSignInWithPassword.mockResolvedValue({
      error: { message: "Email not confirmed", code: "email_not_confirmed" },
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login("test@example.com", "password123");
      })
    ).rejects.toThrow(EMAIL_NOT_CONFIRMED);
  });

  test("resendConfirmation resends the signup email with the redirect URL", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.resendConfirmation("test@example.com");
    });

    expect(mockResend).toHaveBeenCalledWith({
      type: "signup",
      email: "test@example.com",
      options: { emailRedirectTo: `${window.location.origin}/` },
    });
  });
});
