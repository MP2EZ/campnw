import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import { ProBadge } from "../components/ProBadge";
import "./Pricing.css";

export function Pricing() {
  const { user } = useAuth();
  const { billing, checkout } = useBilling();

  const currentTier = billing?.tier || user?.tier || "free";

  return (
    <main className="pricing-page">
      <h1 className="pricing-title">Choose your plan</h1>
      <p className="pricing-subtitle">
        Find the perfect campsite, every time.
      </p>

      <div className="pricing-grid">
        {/* Free tier */}
        <div className={`pricing-card ${currentTier === "free" ? "pricing-current" : ""}`}>
          <div className="pricing-card-header">
            <h2>Free</h2>
            <div className="pricing-price">
              <span className="pricing-amount">$0</span>
              <span className="pricing-period">/month</span>
            </div>
          </div>
          <ul className="pricing-features">
            <li>3 campground watches</li>
            <li>15-minute polling</li>
            <li>3 trip planner sessions/month</li>
            <li>Multi-source search (rec.gov + WA State)</li>
            <li>Calendar heat map</li>
            <li>Push notifications</li>
          </ul>
          {currentTier === "free" && (
            <div className="pricing-current-label">Current plan</div>
          )}
        </div>

        {/* Pro tier */}
        <div className={`pricing-card pricing-card-pro ${currentTier === "pro" ? "pricing-current" : ""}`}>
          <div className="pricing-card-header">
            <h2>Pro <ProBadge /></h2>
            <div className="pricing-price">
              <span className="pricing-amount">$5</span>
              <span className="pricing-period">/month</span>
            </div>
          </div>
          <ul className="pricing-features">
            <li><strong>Unlimited</strong> campground watches</li>
            <li><strong>5-minute</strong> polling (3x faster)</li>
            <li><strong>20</strong> trip planner sessions/month</li>
            <li>Multi-source search (rec.gov + WA State)</li>
            <li>Calendar heat map</li>
            <li>Push notifications</li>
          </ul>
          {currentTier === "pro" ? (
            <div className="pricing-current-label">Current plan</div>
          ) : user ? (
            <button
              className="search-btn pricing-cta"
              onClick={async () => {
                try {
                  await checkout();
                } catch {
                  // redirect happens on success
                }
              }}
            >
              Upgrade to Pro
            </button>
          ) : (
            <p className="pricing-signin-note">
              Sign in to upgrade
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
