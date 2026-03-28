import { useEffect, useRef } from "react";
import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import "./UpgradeModal.css";

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
  reason?: "watch_limit" | "plan_limit";
  onShowAuth?: () => void;
}

export function UpgradeModal({ open, onClose, reason, onShowAuth }: UpgradeModalProps) {
  const { user } = useAuth();
  const { checkout } = useBilling();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

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
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
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

  if (!open) return null;

  const title =
    reason === "watch_limit"
      ? "Watch limit reached"
      : reason === "plan_limit"
        ? "Trip planner limit reached"
        : "Upgrade to Pro";

  const description =
    reason === "watch_limit"
      ? "Free accounts can monitor up to 3 campgrounds. Upgrade to Pro for unlimited watches with faster 5-minute polling."
      : reason === "plan_limit"
        ? "Free accounts get 3 trip planner sessions per month. Upgrade to Pro for 20 sessions per month."
        : "Get unlimited watches, faster polling, and more trip planner sessions.";

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
          <h2 id="upgrade-modal-title">{title}</h2>
          <button className="watch-close" onClick={onClose} ref={closeRef}>
            &times;
          </button>
        </div>

        <div className="upgrade-modal-body">
          <p className="upgrade-description">{description}</p>

          <div className="upgrade-features">
            <div className="upgrade-feature">Unlimited watches</div>
            <div className="upgrade-feature">5-minute polling (3x faster)</div>
            <div className="upgrade-feature">20 trip planner sessions/month</div>
          </div>

          <div className="upgrade-actions">
            {user ? (
              <button
                className="search-btn upgrade-btn"
                onClick={async () => {
                  try {
                    await checkout();
                  } catch {
                    // checkout redirects, errors are rare
                  }
                }}
              >
                Upgrade to Pro
              </button>
            ) : (
              <button
                className="search-btn upgrade-btn"
                onClick={() => {
                  onClose();
                  onShowAuth?.();
                }}
              >
                Sign up to upgrade
              </button>
            )}
            <button className="upgrade-dismiss" onClick={onClose}>
              Maybe later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
