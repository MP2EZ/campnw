import { useState, useEffect, useCallback } from "react";
import {
  getBillingStatus,
  createCheckoutSession,
  createPortalSession,
  type BillingStatus,
} from "../api";
import { useAuth } from "./useAuth";

interface UseBillingReturn {
  billing: BillingStatus | null;
  loading: boolean;
  isPro: boolean;
  checkout: () => Promise<void>;
  portal: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useBilling(): UseBillingReturn {
  const { user } = useAuth();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const status = await getBillingStatus();
      setBilling(status);
    } catch {
      setBilling(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, user?.id]);

  const checkout = useCallback(async () => {
    const { url } = await createCheckoutSession();
    window.location.href = url;
  }, []);

  const portal = useCallback(async () => {
    const { url } = await createPortalSession();
    window.location.href = url;
  }, []);

  return {
    billing,
    loading,
    isPro: billing?.tier === "pro",
    checkout,
    portal,
    refresh,
  };
}
