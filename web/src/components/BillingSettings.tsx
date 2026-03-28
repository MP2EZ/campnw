import { useBilling } from "../hooks/useBilling";
import { ProBadge } from "./ProBadge";
import "./BillingSettings.css";

export function BillingSettings() {
  const { billing, isPro, portal, loading } = useBilling();

  if (loading || !billing) return null;

  return (
    <div className="billing-settings">
      <div className="billing-plan-row">
        <span className="billing-label">Plan</span>
        <span className="billing-value">
          {isPro ? (
            <>Pro <ProBadge /></>
          ) : billing.subscription_status === "grandfathered" ? (
            "Free (grandfathered)"
          ) : (
            "Free"
          )}
        </span>
      </div>

      <div className="billing-plan-row">
        <span className="billing-label">Watches</span>
        <span className="billing-value">
          {billing.current_watches}
          {isPro ? "" : ` / ${billing.max_watches}`}
        </span>
      </div>

      <div className="billing-plan-row">
        <span className="billing-label">Trip planner</span>
        <span className="billing-value">
          {billing.plan_sessions_used} / {billing.plan_sessions_limit} this month
        </span>
      </div>

      {billing.grandfathered_until && (
        <p className="billing-note">
          Your existing watches are preserved until{" "}
          {new Date(billing.grandfathered_until).toLocaleDateString()}.
          Upgrade to Pro to add more.
        </p>
      )}

      {isPro && (
        <button
          className="billing-manage-btn"
          onClick={async () => {
            try {
              await portal();
            } catch {
              // redirect happens
            }
          }}
        >
          Manage billing
        </button>
      )}

      {!isPro && (
        <a href="/pricing" className="billing-upgrade-link">
          View plans
        </a>
      )}
    </div>
  );
}
