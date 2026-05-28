/**
 * UpgradeModal — shown when a free user hits an entitlement gate
 * (e.g., 4th watch creation) OR clicks "Upgrade to Pro" voluntarily.
 *
 * Reuses the watch-overlay / watch-panel chrome from AuthModal for
 * visual consistency. Focus trap + ESC handler match that component's
 * a11y pattern so screen-reader behavior is uniform across modals.
 */

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import { track } from "../api";

type Reason = "watch_limit" | "planner_limit" | "voluntary";

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
  /** What triggered the modal — drives the headline + analytics. */
  reason?: Reason;
  /** Optional context for analytics (e.g., current watch count). */
  contextInfo?: Record<string, string | number>;
}

const HEADLINES: Record<Reason, { title: string; body: string }> = {
  watch_limit: {
    title: "Upgrade for unlimited watches",
    body:
      "Free accounts can track 3 campgrounds at a time. Pro removes the cap so you can watch every place you care about.",
  },
  planner_limit: {
    title: "Upgrade for more trip planner sessions",
    body:
      "Free accounts get 3 trip planner sessions per month. Pro raises that to 20.",
  },
  voluntary: {
    title: "Upgrade to Campable Pro",
    body:
      "Unlimited watches, faster polling, more trip planning. $5/month — keeps the servers running and the project alive.",
  },
};

export function UpgradeModal({
  open,
  onClose,
  reason = "voluntary",
  contextInfo,
}: UpgradeModalProps) {
  const { user } = useAuth();
  const { startCheckout, status } = useBilling();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Initial focus + ESC + focus trap (mirrors AuthModal).
  useEffect(() => {
    if (open && closeRef.current) closeRef.current.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      track("upgrade_modal_shown", { reason, ...(contextInfo || {}) });
    }
    // contextInfo is intentionally not in deps — fire once per open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reason]);

  if (!open) return null;

  const headline = HEADLINES[reason];
  const billingConfigured = status?.configured ?? false;
  const isLoggedIn = !!user;

  const handleUpgrade = async () => {
    setError(null);
    setSubmitting(true);
    track("upgrade_clicked", { reason, ...(contextInfo || {}) });
    try {
      await startCheckout();
      // Redirect happens inside startCheckout → no further code runs
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout unavailable");
      setSubmitting(false);
    }
  };

  return (
    <div className="watch-overlay" onClick={onClose}>
      <div
        className="watch-panel upgrade-modal"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="upgrade-modal-title"
      >
        <div className="watch-panel-header">
          <h2 id="upgrade-modal-title">{headline.title}</h2>
          <button
            className="watch-close"
            onClick={onClose}
            ref={closeRef}
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="upgrade-body">
          <p className="upgrade-tagline">{headline.body}</p>

          <ul className="upgrade-features">
            <li>Unlimited watches (vs 3 free)</li>
            <li>5-minute polling (vs 15 free)</li>
            <li>20 trip planner sessions/month (vs 3 free)</li>
            <li>Anomaly-based deal alerts</li>
            <li>Cancel anytime via portal</li>
          </ul>

          <div className="upgrade-price">
            <span className="upgrade-price-amount">$5</span>
            <span className="upgrade-price-period">/ month</span>
          </div>

          {error && (
            <p className="auth-error" role="alert">{error}</p>
          )}

          {!isLoggedIn ? (
            <p className="upgrade-prompt-signin">
              Sign in first, then upgrade from your account menu.
            </p>
          ) : !billingConfigured ? (
            <p className="upgrade-prompt-signin" role="status">
              Pro upgrades aren&rsquo;t live yet. Check back soon.
            </p>
          ) : (
            <button
              type="button"
              className="btn-primary upgrade-cta"
              onClick={handleUpgrade}
              disabled={submitting}
            >
              {submitting ? "Opening Stripe…" : "Upgrade to Pro"}
            </button>
          )}

          <p className="upgrade-fine-print">
            Payments handled by Stripe. Cards are never stored on
            Campable&rsquo;s servers.
          </p>
        </div>
      </div>
    </div>
  );
}
