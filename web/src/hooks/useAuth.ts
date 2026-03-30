import { createContext, useContext, useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getMe, login, signup, logout, updateProfile, track, type UserData } from "../api";
import { createElement } from "react";

interface AuthContextValue {
  user: UserData | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (updates: Partial<Omit<UserData, "id" | "email">>) => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const u = await getMe();
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const identifyUser = useCallback((u: UserData) => {
    import("posthog-js").then(({ default: posthog }) => {
      posthog.identify(String(u.id), {
        display_name: u.display_name,
      });
    }).catch(() => {});
  }, []);

  const handleLogin = useCallback(async (email: string, password: string) => {
    const u = await login(email, password);
    setUser(u);
    identifyUser(u);
    track("login", {});
  }, [identifyUser]);

  const handleSignup = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const u = await signup(email, password, displayName);
      setUser(u);
      identifyUser(u);
      track("signup", {});
    },
    [identifyUser]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    setUser(null);
    import("posthog-js").then(({ default: posthog }) => {
      posthog.reset();
    }).catch(() => {});
  }, []);

  const handleUpdateProfile = useCallback(
    async (updates: Partial<Omit<UserData, "id" | "email">>) => {
      const u = await updateProfile(updates);
      setUser(u);
    },
    []
  );

  return createElement(
    AuthContext.Provider,
    {
      value: {
        user,
        loading,
        login: handleLogin,
        signup: handleSignup,
        logout: handleLogout,
        updateProfile: handleUpdateProfile,
        refresh,
      },
    },
    children
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
