/**
 * Pricing page (/pricing) — v1.4 monetization.
 *
 * Single source of truth for the Free vs Pro comparison. Linked from
 * UpgradeModal, footer, and SEO upgrade CTAs. Reads billing status
 * from useBilling so the CTA reflects the user's current tier:
 *   - Anonymous: "Sign in to upgrade"
 *   - Free + logged in: "Upgrade to Pro" (starts Stripe Checkout)
 *   - Pro: "Manage billing" (opens Stripe Portal)
 */

import { useEffect, useState } from "react";
import { Helmet } from "react-helmet-async";
import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import { track } from "../api";

interface Row {
  feature: string;
  free: string;
  pro: string;
}

const COMPARISON: Row[] = [
  { feature: "Search (all providers, all filters)", free: "Unlimited", pro: "Unlimited" },
  { feature: "Calendar heat map, smart search, vibes", free: "Yes", pro: "Yes" },
  { feature: "Booking links + shareable searches", free: "Yes", pro: "Yes" },
  { feature: "Simultaneous active watches", free: "3", pro: "Unlimited" },
  { feature: "Watch polling interval", free: "15 min", pro: "5 min" },
  { feature: "Trip planner sessions per month", free: "3", pro: "20" },
  { feature: "Anomaly-based deal alerts", free: "—", pro: "Yes" },
  { feature: "Data export + account deletion", free: "Yes", pro: "Yes" },
];

export default function Pricing() {
  const { user } = useAuth();
  const { isPro, startCheckout, openPortal, status, loading } = useBilling();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    track("pricing_page_viewed", { is_pro: isPro ? 1 : 0 });
  }, [isPro]);

  const handleUpgrade = async () => {
    setError(null);
    setSubmitting(true);
    track("upgrade_clicked", { reason: "pricing_page" });
    try {
      await startCheckout();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout unavailable");
      setSubmitting(false);
    }
  };

  const handleManage = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await openPortal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal unavailable");
      setSubmitting(false);
    }
  };

  return (
    <>
      <Helmet>
        <title>Pricing · Campable</title>
        <meta
          name="description"
          content="Campable is free for search and 3 watches. Pro is $5/month for unlimited watches, faster polling, and deal alerts."
        />
      </Helmet>

      <main className="pricing-page">
        <header className="pricing-header">
          <h1>Pricing that pays for the servers</h1>
          <p className="pricing-lede">
            Campable is built by one person. The free tier covers what most
            campers need — search, three watches, and shareable links.
            Pro covers what enthusiasts want, and the $5/month keeps the
            polling engine running for everyone.
          </p>
        </header>

        <section className="pricing-cards" aria-labelledby="plans-heading">
          <h2 id="plans-heading" className="sr-only">Plan comparison</h2>

          <article className="pricing-card pricing-card-free">
            <h3>Free</h3>
            <p className="pricing-card-price">$0</p>
            <p className="pricing-card-subtitle">Always free, no signup required for search</p>
            <ul className="pricing-card-features">
              <li>All search + discovery features</li>
              <li>3 watches with 15-min polling</li>
              <li>3 trip planner sessions/month</li>
              <li>Web push + email notifications</li>
            </ul>
          </article>

          <article className="pricing-card pricing-card-pro" aria-labelledby="pro-heading">
            <h3 id="pro-heading">Pro</h3>
            <p className="pricing-card-price">
              $5<span className="pricing-card-period">/month</span>
            </p>
            <p className="pricing-card-subtitle">For trip planners and serial campers</p>
            <ul className="pricing-card-features">
              <li>Unlimited watches</li>
              <li>5-min polling for time-sensitive openings</li>
              <li>20 trip planner sessions/month</li>
              <li>Anomaly-based deal alerts</li>
              <li>Cancel anytime via Stripe portal</li>
            </ul>

            {error && (
              <p className="auth-error" role="alert">{error}</p>
            )}

            {loading ? (
              <button type="button" className="btn-primary" disabled>
                Loading…
              </button>
            ) : !user ? (
              <p className="pricing-cta-note">Sign in to upgrade.</p>
            ) : isPro ? (
              <button
                type="button"
                className="btn-primary"
                onClick={handleManage}
                disabled={submitting}
              >
                {submitting ? "Opening portal…" : "Manage billing"}
              </button>
            ) : status?.configured ? (
              <button
                type="button"
                className="btn-primary"
                onClick={handleUpgrade}
                disabled={submitting}
              >
                {submitting ? "Opening Stripe…" : "Upgrade to Pro"}
              </button>
            ) : (
              <p className="pricing-cta-note" role="status">
                Pro upgrades aren&rsquo;t live yet. Check back soon.
              </p>
            )}
          </article>
        </section>

        <section className="pricing-table-wrap" aria-labelledby="comparison-heading">
          <h2 id="comparison-heading">What you get</h2>
          <table className="pricing-table">
            <thead>
              <tr>
                <th scope="col">Feature</th>
                <th scope="col">Free</th>
                <th scope="col">Pro</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row) => (
                <tr key={row.feature}>
                  <th scope="row">{row.feature}</th>
                  <td>{row.free}</td>
                  <td>{row.pro}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="pricing-faq" aria-labelledby="faq-heading">
          <h2 id="faq-heading">A few honest answers</h2>
          <dl>
            <dt>Will the free tier always be free?</dt>
            <dd>Yes. Search and basic monitoring stay free indefinitely.</dd>

            <dt>How do I cancel?</dt>
            <dd>
              One click in the Stripe portal. You keep Pro access through the
              end of your paid period.
            </dd>

            <dt>What happens to my watches if I downgrade?</dt>
            <dd>
              They&rsquo;re paused, never deleted. Re-enable them by upgrading
              again — no data loss.
            </dd>

            <dt>Where do payments go?</dt>
            <dd>
              Directly to Stripe. Campable never sees or stores your card
              number.
            </dd>
          </dl>
        </section>
      </main>
    </>
  );
}
