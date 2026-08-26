import { useEffect, useState } from "react";
import { Helmet } from "react-helmet-async";
import { Link, useParams } from "react-router-dom";
import {
  ShareUnavailableError,
  getPosthog,
  getSharedLink,
  track,
  type SharedLinkPayload,
} from "../api";
import { formatDateRange } from "../lib/dates";
import { SOURCE_LABELS } from "../lib/sources";

/**
 * Landing page for a shared watch or trip.
 *
 * ShareButton has always copied `${origin}/shared/${uuid}`, and the server has
 * always served that payload — but no client route matched it, so the SPA
 * booted and rendered an empty content area. Recipients got a blank page with
 * no error and no redirect, which made the share feature look like it worked
 * for the sharer and do nothing for everyone else.
 */
export default function SharedView() {
  const { uuid = "" } = useParams();
  const [payload, setPayload] = useState<SharedLinkPayload | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    getSharedLink(uuid)
      .then((data) => {
        if (!active) return;
        setPayload(data);
        track("share_link_landed", {
          share_type: data.type || "unknown",
          referrer_domain: safeReferrerDomain(),
        });
        // First-touch attribution: a recipient who later signs up should be
        // creditable to the share loop rather than to direct traffic.
        getPosthog()?.setPersonProperties(undefined, {
          acquisition_channel: "share",
        });
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ShareUnavailableError) {
          setUnavailable(err.kind);
          track("share_link_unavailable", { reason: err.kind });
        } else {
          setFailed(true);
        }
      });
    return () => {
      active = false;
    };
  }, [uuid]);

  if (unavailable) {
    return (
      <div className="shared-view">
        <Helmet><title>Link unavailable · Campable</title></Helmet>
        <h1>This link isn&rsquo;t available</h1>
        <p className="shared-view-note">
          {unavailable === "gone"
            ? "It was revoked by whoever shared it, or it has expired."
            : unavailable === "rate_limited"
              ? "This link has been opened a lot recently. Try again in a few minutes."
              : "We couldn't find it. Double-check the link, or ask for a new one."}
        </p>
        <Link className="btn-primary" to="/">Search campsites</Link>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="shared-view">
        <div className="error-banner" role="alert">
          Couldn&rsquo;t load that link. Please try again.
        </div>
        <Link className="btn-primary" to="/">Search campsites</Link>
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="shared-view" aria-busy="true">
        <p className="shared-view-note">Loading…</p>
      </div>
    );
  }

  const title =
    payload.type === "watch"
      ? payload.watch?.name || "Shared watch"
      : payload.trip?.name || "Shared trip";

  return (
    <div className="shared-view">
      <Helmet><title>{title} · Campable</title></Helmet>

      <p className="shared-view-kicker">
        {payload.type === "watch" ? "Shared campsite watch" : "Shared trip"}
      </p>
      <h1>{title}</h1>

      {payload.type === "watch" && payload.watch && (
        <div className="shared-view-body">
          <p className="shared-view-dates">
            {formatDateRange(payload.watch.start_date, payload.watch.end_date)}
            {payload.watch.min_nights > 1 && ` · ${payload.watch.min_nights}+ nights`}
          </p>
          <p className="shared-view-note">
            Campable checks this campground every 15 minutes and sends an alert
            the moment a site frees up.
          </p>
        </div>
      )}

      {payload.type === "trip" && payload.trip && (
        <div className="shared-view-body">
          <p className="shared-view-dates">
            {formatDateRange(payload.trip.start_date, payload.trip.end_date)}
          </p>
          <ul className="shared-view-list">
            {payload.trip.campgrounds.map((cg) => (
              <li key={`${cg.source}-${cg.facility_id}`}>
                <span className="shared-view-cg">{cg.name}</span>
                <span className="shared-view-source">
                  {SOURCE_LABELS[cg.source] || cg.source}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="shared-view-cta">
        <Link
          className="btn-primary"
          to="/"
          onClick={() =>
            track("share_link_cta_clicked", {
              share_type: payload.type || "unknown",
            })
          }
        >
          Find your own campsite
        </Link>
      </div>
    </div>
  );
}

/** Referrer host only — never the full URL, which can carry query params. */
function safeReferrerDomain(): string {
  try {
    return document.referrer ? new URL(document.referrer).hostname : "direct";
  } catch {
    return "unknown";
  }
}
