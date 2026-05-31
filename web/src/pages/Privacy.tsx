import { Helmet } from "react-helmet-async";

export default function Privacy() {
  return (
    <>
      <Helmet>
        <title>Privacy · Campable</title>
        <meta
          name="description"
          content="What Campable collects, the third parties that touch your data, retention, and how to exercise your access and deletion rights."
        />
      </Helmet>

      <main className="legal-page" id="main-content">
        <header className="legal-header">
          <h1>Privacy Policy</h1>
          <p className="legal-meta">Last updated: 2026-05-31</p>
          <p className="about-lede">
            Campable is a campsite discovery tool. To run search, watches, and
            billing we collect the minimum data needed and route it through a
            short list of specific third parties &mdash; named below, not
            described as &ldquo;service providers.&rdquo; No ads, no selling, no
            cross-site tracking pixels.
          </p>
        </header>

        <section className="legal-section" aria-labelledby="collect-heading">
          <h2 id="collect-heading">What we collect</h2>
          <ul className="about-list">
            <li>
              <strong>Account</strong> &mdash; email, a password (hashed and
              stored by Supabase, never seen in plaintext on our servers), and
              an optional display name.
            </li>
            <li>
              <strong>Product data</strong> &mdash; the watches, trips, and
              search history you create. Stored against your account so they
              persist across devices.
            </li>
            <li>
              <strong>Billing</strong> &mdash; Stripe customer ID and
              subscription status. We never see your card number; Stripe handles
              card data directly.
            </li>
            <li>
              <strong>Analytics</strong> &mdash; page views, button clicks,
              search parameters. Analytics requests are reverse-proxied
              through campable.co so your IP isn&rsquo;t forwarded to the
              analytics vendor.
            </li>
            <li>
              <strong>Server logs</strong> &mdash; standard HTTP request
              metadata for debugging and abuse prevention. Retained 30 days.
            </li>
          </ul>
        </section>

        <section className="legal-section" aria-labelledby="parties-heading">
          <h2 id="parties-heading">Third parties that touch your data</h2>
          <ul className="about-list">
            <li>
              <strong>Supabase</strong> &mdash; authentication and our primary
              database. US-hosted. Sees your email, hashed password, and all
              account-tied data.
            </li>
            <li>
              <strong>Stripe</strong> &mdash; payment processing. Sees your
              billing details directly; we receive only a customer ID and
              subscription status.
            </li>
            <li>
              <strong>PostHog</strong> &mdash; product analytics, EU-hosted
              (eu.posthog.com). Sees clicks and page views tied to a session
              ID. Requests are reverse-proxied through campable.co so your
              IP isn&rsquo;t forwarded.
            </li>
            <li>
              <strong>Mapbox</strong> &mdash; drive-time geocoding. Sees the
              origin and destination coordinates required to compute a route.
              Does not see your account.
            </li>
            <li>
              <strong>Visual Crossing</strong> &mdash; weather climate normals.
              Called server-side with campground coordinates only. Never sees
              user identity.
            </li>
            <li>
              <strong>Cloudflare</strong> &mdash; DNS and TLS termination. Sees
              standard HTTP request metadata.
            </li>
            <li>
              <strong>Fly.io</strong> &mdash; application hosting. Holds the
              running application and its database.
            </li>
          </ul>
        </section>

        <section className="legal-section" aria-labelledby="dont-heading">
          <h2 id="dont-heading">What we don&rsquo;t do</h2>
          <p>
            No advertising network integrations. No selling or renting of your
            data. No cross-site tracking pixels. No third-party social-login
            providers wired in yet (when Google/Apple sign-in lands, this
            section will be updated to disclose what each provider sees).
          </p>
        </section>

        <section className="legal-section" aria-labelledby="retention-heading">
          <h2 id="retention-heading">Retention</h2>
          <p>
            Account data lives until you delete your account, at which point
            it&rsquo;s removed from our database within 7 days. Billing records
            are retained per Stripe&rsquo;s tax and audit requirements (up to
            7 years). Analytics events are retained 12 months in aggregate
            form. Server logs are retained 30 days.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="rights-heading">
          <h2 id="rights-heading">Your rights</h2>
          <p>
            Under GDPR (EU/UK) and CCPA (California) you have the right to
            access, correct, delete, or export your data, and to object to
            certain processing. Email{" "}
            <a href="mailto:hello@palouselabs.com">hello@palouselabs.com</a>{" "}
            and we&rsquo;ll act on it within 30 days. Account deletion is also
            available directly in the user menu.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="cookies-heading">
          <h2 id="cookies-heading">Cookies and analytics</h2>
          <p>
            We use first-party cookies for session login and a first-party
            analytics cookie for PostHog. No third-party advertising cookies.
            We have not yet implemented an EU consent banner; we plan to add
            one once EU traffic exceeds 5% of total. If you&rsquo;re in the EU
            and want to opt out before then, email us and we&rsquo;ll exclude
            your account from analytics.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="children-heading">
          <h2 id="children-heading">Children</h2>
          <p>
            Campable is not directed at people under 13 and we do not knowingly
            collect their data.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="changes-heading">
          <h2 id="changes-heading">Changes</h2>
          <p>
            Material changes to this policy will be announced in-app and by
            email to active subscribers. Minor edits (wording, clarifications)
            are made silently and reflected in the &ldquo;Last updated&rdquo;
            date at the top.
          </p>
        </section>

        <section className="legal-section" aria-labelledby="contact-heading">
          <h2 id="contact-heading">Contact</h2>
          <p>
            Privacy questions or data requests:{" "}
            <a href="mailto:hello@palouselabs.com">hello@palouselabs.com</a>.
            Replies come from a real human.
          </p>
        </section>
      </main>
    </>
  );
}
