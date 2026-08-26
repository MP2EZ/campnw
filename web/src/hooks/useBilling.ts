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
import { Capacitor } from "@capacitor/core";
import { Browser } from "@capacitor/browser";
import {
  getBillingStatus,
  getPosthog,
  track,
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
      // Registering plan as a super property makes every subsequent event
      // segmentable by tier without touching any individual call site.
      getPosthog()?.register({
        plan: s.is_pro ? "pro" : "free",
        subscription_status: s.subscription_status,
      });
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
      track("checkout_returned", { outcome: "success" });
      refresh();
      params.delete("billing");
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname + (newSearch ? `?${newSearch}` : "");
      window.history.replaceState({}, "", newUrl);
    }
  }, [refresh]);

  const handleStartCheckout = useCallback(async () => {
    // Option A (v1.45): the native app sells nothing in-app (no StoreKit IAP).
    // Send users to the web pricing page in the system browser to upgrade as a
    // web session. No backend checkout call from native.
    if (Capacitor.isNativePlatform()) {
      // SFSafariViewController has its own cookie jar, so PostHog mints a
      // fresh anonymous id over there and the upgrade reads as web-direct.
      // Pass the distinct id through so the web session can stitch back.
      const distinctId = getPosthog()?.get_distinct_id?.() ?? "";
      track("native_upgrade_handoff", { platform: "ios", has_distinct_id: distinctId ? 1 : 0 });
      const url = new URL("https://campable.co/pricing");
      url.searchParams.set("utm_source", "ios_app");
      url.searchParams.set("utm_medium", "native_handoff");
      if (distinctId) url.searchParams.set("ph_distinct_id", distinctId);
      await Browser.open({ url: url.toString() });
      return;
    }
    // upgrade_clicked fires *before* this await, so it counts intent, not
    // checkout entries: a 503 (billing unconfigured) or 502 (Stripe down)
    // inflated it with failures. These two split that.
    try {
      const url = await startCheckout();
      track("checkout_session_created", {});
      window.location.href = url;
    } catch (err) {
      track("checkout_failed", {
        reason: err instanceof Error ? err.message.slice(0, 80) : "unknown",
      });
      throw err;
    }
  }, []);

  const handleOpenPortal = useCallback(async () => {
    const url = await openBillingPortal();
    // Managing an existing subscription (cancel/update) is not a purchase, so
    // opening the authenticated Stripe portal in the system browser is fine.
    if (Capacitor.isNativePlatform()) {
      await Browser.open({ url });
      return;
    }
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
