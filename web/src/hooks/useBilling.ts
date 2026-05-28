/**
 * Billing context hook (v1.4 monetization).
 *
 * Fetches /api/billing/status once on mount and exposes the tier state
 * plus action helpers (startCheckout, openPortal, refresh). Shared via
 * a context so multiple components (UpgradeModal, WatchPanel, UserMenu)
 * read consistent state without re-fetching.
 */

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  getBillingStatus,
  openBillingPortal,
  startCheckout,
  type BillingStatus,
} from "../api";
import { useAuth } from "./useAuth";

interface BillingContextValue {
  status: BillingStatus | null;
  loading: boolean;
  isPro: boolean;
  /** null means unlimited (Pro); a number is the free-tier cap. */
  watchLimit: number | null;
  /** Re-fetch /api/billing/status. Call after returning from Stripe. */
  refresh: () => Promise<void>;
  /** Start checkout and redirect the browser. Throws if Stripe unconfigured. */
  startCheckout: () => Promise<void>;
  /** Open Stripe Customer Portal in the same tab. */
  openPortal: () => Promise<void>;
}

const BillingContext = createContext<BillingContextValue | null>(null);

const FREE_FALLBACK: BillingStatus = {
  subscription_status: "free",
  subscription_expires_at: "",
  has_stripe_customer: false,
  is_pro: false,
  watch_limit: 3,
  planner_session_limit: 3,
  configured: false,
};

export function BillingProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const s = await getBillingStatus();
      setStatus(s);
    } catch {
      // Endpoint unreachable — render as if free-tier so UI doesn't break.
      setStatus(FREE_FALLBACK);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch and re-fetch on auth state change (login/logout flips
  // the relevant subscription_status on the user record).
  useEffect(() => {
    if (authLoading) return;
    refresh();
  }, [user?.id, authLoading, refresh]);

  // Handle return from Stripe Checkout success: refresh once when the
  // ?billing=success query param is present, then strip it from the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("billing") === "success") {
      refresh();
      params.delete("billing");
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname + (newSearch ? `?${newSearch}` : "");
      window.history.replaceState({}, "", newUrl);
    }
  }, [refresh]);

  const handleStartCheckout = useCallback(async () => {
    const url = await startCheckout();
    window.location.href = url;
  }, []);

  const handleOpenPortal = useCallback(async () => {
    const url = await openBillingPortal();
    window.location.href = url;
  }, []);

  // watchLimit: `??` would coerce null (Pro unlimited) to the fallback,
  // turning Pro users into free-tier UI. Branch on status presence instead.
  const value: BillingContextValue = {
    status,
    loading,
    isPro: status?.is_pro ?? false,
    watchLimit: status ? status.watch_limit : 3,
    refresh,
    startCheckout: handleStartCheckout,
    openPortal: handleOpenPortal,
  };

  return createElement(BillingContext.Provider, { value }, children);
}

export function useBilling(): BillingContextValue {
  const ctx = useContext(BillingContext);
  if (!ctx) {
    throw new Error("useBilling must be used within BillingProvider");
  }
  return ctx;
}
