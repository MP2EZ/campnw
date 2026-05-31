import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";

export default function Terms() {
  return (
    <>
      <Helmet>
        <title>Terms · Campable</title>
        <meta
          name="description"
          content="The deal, the refund policy, acceptable use, and the legal small print for Campable and Campable Pro."
        />
      </Helmet>

      <main className="legal-page" id="main-content">
        <header className="legal-header">
          <h1>Terms of Service</h1>
          <p className="legal-meta">Last updated: 2026-05-31</p>
          <p className="about-lede">
            Plain-English summary: use Campable in good faith, don&rsquo;t scrape
            our scrape, cancel Pro any time in one click, and we&rsquo;ll do our
            best to keep the data accurate but campsite availability is
            ultimately what the booking site says it is.
          </p>
        </header>

        <section className="legal-section" aria-labelledby="deal-heading">
          <h2 id="deal-heading">The deal</h2>
          <p>
            The <strong>free tier</strong> covers unlimited search across all
            providers, three simultaneous active watches with 15-minute polling,
            and shareable result links. It is genuinely free &mdash; no trial,
            no card on file, no daily limits.
          </p>
          <p>
            <strong>Campable Pro</strong> is $5/month. It unlocks unlimited
            simultaneous watches, 5-minute polling instead of 15-minute, more
            trip-planner sessions per month, and anomaly-based deal alerts. See{" "}
            <Link to="/pricing">/pricing</Link> for the full comparison.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="refund-heading">
          <h2 id="refund-heading">Refund policy</h2>
          <p>
            If Pro isn&rsquo;t doing what you wanted, email{" "}
            <a href="mailto:hello@palouselabs.com">hello@palouselabs.com</a>{" "}
            within 30 days of charge and we&rsquo;ll refund it. No forms, no
            survey, no questions about whether you really tried it. After 30
            days, cancel in one click via the Stripe portal and you won&rsquo;t
            be charged again, but the current period isn&rsquo;t refunded.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="use-heading">
          <h2 id="use-heading">Acceptable use</h2>
          <p>
            Don&rsquo;t scrape Campable to rebuild it elsewhere. Don&rsquo;t use
            it to automate bookings or arbitrage. Don&rsquo;t create multiple
            accounts to exceed free-tier limits. Don&rsquo;t attempt to break
            authentication, billing, or notification systems. Use the watch and
            alert features for personal trip planning, not commercial resale.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="termination-heading">
          <h2 id="termination-heading">Termination</h2>
          <p>
            You can cancel Pro any time via the Stripe Customer Portal and
            delete your account from the user menu. We may suspend or terminate
            accounts that violate the acceptable-use rules, abuse the system,
            or chargeback Pro charges without first contacting us.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="warranty-heading">
          <h2 id="warranty-heading">No warranty on availability data</h2>
          <p>
            Campsite availability is fetched from third-party booking systems
            (Recreation.gov, Washington State Parks, Oregon State Parks). We
            cache and aggregate it but we can&rsquo;t guarantee it&rsquo;s
            accurate at any given moment &mdash; availability flips faster than
            our polling interval, and the underlying systems occasionally
            return stale data. Always confirm on the booking site before
            booking.
          </p>
          <p>
            Campable does not process bookings or take a cut of reservations.
            When you click &ldquo;Book,&rdquo; you go directly to the operator
            and pay them. We have no role in the reservation contract between
            you and the operator.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="liability-heading">
          <h2 id="liability-heading">Limitation of liability</h2>
          <p>
            To the maximum extent allowed by law, Campable&rsquo;s liability
            for any claim arising from your use of the service is limited to
            the fees you paid in the 12 months preceding the claim. The service
            is provided &ldquo;as is&rdquo; without warranty of merchantability
            or fitness for a particular purpose. This does not limit liability
            for things that can&rsquo;t legally be limited (gross negligence,
            willful misconduct, statutory consumer rights).
          </p>
        </section>

        <section className="legal-section" aria-labelledby="law-heading">
          <h2 id="law-heading">Governing law</h2>
          <p>
            These terms are governed by the laws of the State of Washington,
            USA, without regard to conflict-of-law rules. Disputes are
            resolved in the state and federal courts of King County,
            Washington.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="changes-heading">
          <h2 id="changes-heading">Changes to these terms</h2>
          <p>
            Material changes will be announced in-app and emailed to active
            subscribers at least 14 days before they take effect. Continued
            use after the effective date constitutes acceptance. If you
            don&rsquo;t accept, cancel before the date and we&rsquo;ll refund
            the unused portion of any pre-paid period.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="contact-heading">
          <h2 id="contact-heading">Contact</h2>
          <p>
            Questions about these terms, the refund policy, or anything else:{" "}
            <a href="mailto:hello@palouselabs.com">hello@palouselabs.com</a>.
          </p>
        </section>
      </main>
    </>
  );
}
