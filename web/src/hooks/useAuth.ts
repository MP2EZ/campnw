import { createContext, useContext, useCallback, useEffect, useState, useRef } from "react";
import type { ReactNode } from "react";
import { createElement } from "react";
import { supabase } from "../lib/supabase";
import { getMe, updateProfile, track, type UserData } from "../api";

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
  const initializedRef = useRef(false);

  const identifyUser = useCallback((u: UserData) => {
    import("posthog-js").then(({ default: posthog }) => {
      posthog.identify(String(u.id), {
        display_name: u.display_name,
      });
    }).catch(() => {});
  }, []);

  const refresh = useCallback(async () => {
    try {
      const u = await getMe();
      setUser(u);
      if (u) identifyUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [identifyUser]);

  // Listen to Supabase auth state changes
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (session) {
          // Fetch local profile (triggers auto-provisioning on backend)
          const u = await getMe();
          setUser(u);
          if (u) identifyUser(u);
        } else {
          setUser(null);
        }
        setLoading(false);
        initializedRef.current = true;
      }
    );

    // If no auth event fires within 500ms, stop showing loading
    const timeout = setTimeout(() => {
      if (!initializedRef.current) setLoading(false);
    }, 500);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [identifyUser]);

  const handleLogin = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
    track("login", {});
    // onAuthStateChange fires → fetches profile and sets user
  }, []);

  const handleSignup = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { display_name: displayName || "" } },
      });
      if (error) throw new Error(error.message);
      track("signup", {});
      // onAuthStateChange fires → fetches profile and sets user
    },
    []
  );

  const handleLogout = useCallback(async () => {
    await supabase.auth.signOut();
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
