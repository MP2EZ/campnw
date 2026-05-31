/**
 * About page (/about) for v1.42.
 *
 * Trust signal for fence-sitters on /pricing. Same first-person,
 * no-marketing voice as the Pricing page. Built to be skimmed
 * top-to-bottom in 60 seconds by someone deciding whether to give
 * a $5/mo subscription to a stranger on the internet. Concrete facts
 * (data sources, funding model) carry more weight than "we're committed
 * to quality" copy ever would.
 */

import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";

export default function About() {
  return (
    <>
      <Helmet>
        <title>About · Campable</title>
        <meta
          name="description"
          content="Campable is a campsite discovery tool for the western US, built by one person, funded by $5/month Pro subscriptions. No ads, no data selling, one-click cancel."
        />
      </Helmet>

      <main className="about-page" id="main-content">
        <header className="about-header">
          <h1>About Campable</h1>
          <p className="about-lede">
            Campable aggregates real-time campsite availability across
            Recreation.gov, Washington State Parks, and Oregon State Parks so
            you can answer &ldquo;what&rsquo;s actually open this weekend
            within driving distance?&rdquo; without bouncing between five
            booking sites.
          </p>
        </header>

        <section className="about-section" aria-labelledby="why-heading">
          <h2 id="why-heading">Why this exists</h2>
          <p>
            Finding a campsite shouldn&rsquo;t require fifteen browser tabs
            and a spreadsheet. The booking sites are designed for people who
            already know the campground they want. They&rsquo;re not designed
            for &ldquo;anywhere quiet and pretty within three hours of
            Seattle&rdquo; or &ldquo;any lakeside spot that opened up this
            week.&rdquo;
          </p>
          <p>
            Campable does the cross-source aggregation, the date filtering,
            the drive-time math, and the trail / lake / old-growth tagging,
            so you can spend less time searching and more time camping.
          </p>
        </section>

        <section className="about-section" aria-labelledby="who-heading">
          <h2 id="who-heading">Who&rsquo;s behind it</h2>
          <p>
            Built and maintained by one person. The kind of person who has
            watched availability flip from open to gone in fifteen minutes
            and decided the booking layer needed a search engine on top.
          </p>
          <p>
            If something&rsquo;s broken or could be better, email{" "}
            <a href="mailto:hello@campable.co">hello@campable.co</a>.
            Replies come from a real human.
          </p>
        </section>

        <section className="about-section" aria-labelledby="funding-heading">
          <h2 id="funding-heading">How it&rsquo;s funded</h2>
          <p>
            Free for search, three watches, and shareable links.{" "}
            <Link to="/pricing">Pro</Link> ($5/month) unlocks unlimited
            watches, 5-minute polling instead of 15-minute, more trip
            planner sessions, and anomaly-based deal alerts. Pro
            subscriptions cover the polling infrastructure and let the free
            tier stay genuinely free for the next person who just needs to
            find a tent site.
          </p>
          <p>
            No ads. We don&rsquo;t sell your data. Pro never auto-converts
            from a trial; it&rsquo;s opt-in, and you can cancel in one click
            from the Stripe portal.
          </p>
        </section>

        <section className="about-section" aria-labelledby="data-heading">
          <h2 id="data-heading">Where the data comes from</h2>
          <ul className="about-list">
            <li>
              <strong>Recreation.gov:</strong> federal campgrounds via the
              official RIDB metadata API and per-day availability endpoint.
            </li>
            <li>
              <strong>Washington State Parks:</strong> via the GoingToCamp
              public API.
            </li>
            <li>
              <strong>Oregon State Parks:</strong> via ReserveAmerica.
            </li>
            <li>
              <strong>Mapbox:</strong> real drive-time routing for the
              distance estimates, rather than straight-line distance.
            </li>
            <li>
              <strong>Visual Crossing:</strong> typical climate normals shown
              on result cards so you know what to pack.
            </li>
          </ul>
          <p>
            When you click &ldquo;Book&rdquo; on a result, you go directly to
            the booking site for that campground. Campable doesn&rsquo;t
            process bookings or take a cut. Payments go to whoever runs the
            campground.
          </p>
        </section>

        <section className="about-section" aria-labelledby="next-heading">
          <h2 id="next-heading">What&rsquo;s coming</h2>
          <p>
            Native iOS and Android apps via Capacitor (later this year, after
            monetization is validated on the web). Predictive availability
            (&ldquo;typically frees up X days before&rdquo;) once polling
            history is deep enough to make confidence bands meaningful
            (around Q1 2027). Continued registry expansion as state park APIs
            become accessible.
          </p>
        </section>
      </main>
    </>
  );
}
