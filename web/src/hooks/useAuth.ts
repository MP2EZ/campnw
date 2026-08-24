import { createContext, useContext, useCallback, useEffect, useState, useRef } from "react";
import type { ReactNode } from "react";
import { createElement } from "react";
import { supabase } from "../lib/supabase";
import { getMe, updateProfile, track, getPosthog, type UserData } from "../api";

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

  // Must use the snippet-initialized instance (see getPosthog in api.ts) —
  // identify() on the npm module singleton is a silent no-op, which left every
  // event anonymous and un-stitched.
  const identifyUser = useCallback((u: UserData) => {
    getPosthog()?.identify(String(u.id), {
      display_name: u.display_name,
    });
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

  // Listen to Supabase auth state changes.
  //
  // supabase-js v2's INITIAL_SESSION event has known race-condition issues
  // with React effect registration — if the listener is registered after
  // the SDK finishes reading localStorage, the event fires before anyone is
  // listening and the persisted session is silently dropped. Symptoms:
  // returning users see "Loading…" forever (user state stays null) even
  // though localStorage has a valid session.
  //
  // Fix: read the persisted session explicitly via getSession() on mount.
  // Register the listener separately for future SIGNED_IN / SIGNED_OUT /
  // TOKEN_REFRESHED events. The `mounted` flag prevents setState after
  // unmount when these calls race with route changes.
  useEffect(() => {
    let mounted = true;

    const applySession = async (session: { access_token: string } | null) => {
      if (!mounted) return;
      if (session) {
        try {
          const u = await getMe();
          if (!mounted) return;
          setUser(u);
          if (u) identifyUser(u);
        } catch {
          if (mounted) setUser(null);
        }
      } else {
        setUser(null);
      }
      if (mounted) {
        setLoading(false);
        initializedRef.current = true;
      }
    };

    // Read any persisted session (writes happen synchronously from
    // localStorage; the Promise resolves on the microtask after the SDK
    // validates it).
    supabase.auth.getSession().then(({ data: { session } }) => {
      applySession(session);
    }).catch(() => {
      if (mounted) setLoading(false);
    });

    // Listen for state changes after initial load
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => { applySession(session); }
    );

    // Failsafe: Supabase unreachable → unblock UI for anonymous browsing
    const timeout = setTimeout(() => {
      if (!initializedRef.current && mounted) setLoading(false);
    }, 500);

    return () => {
      mounted = false;
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
    // Without a real reset the next person to sign in on this device is
    // merged into the previous user's profile.
    getPosthog()?.reset();
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
