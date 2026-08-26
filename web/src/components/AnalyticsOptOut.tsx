import { useEffect, useState } from "react";
import { getPosthog, track } from "../api";

/**
 * Per-device analytics opt-out.
 *
 * The privacy page described PostHog as seeing "clicks and page views" while
 * index.html also enabled session replay, and `opt_out_capturing` appeared
 * nowhere in the app — so the only route out was emailing support. This is the
 * in-product control that disclosure implies.
 *
 * PostHog persists the choice in its own localStorage entry, so it survives
 * reloads but is per-browser; the copy alongside says so rather than implying
 * an account-wide setting.
 */
export function AnalyticsOptOut() {
  const [optedOut, setOptedOut] = useState<boolean | null>(null);

  useEffect(() => {
    const ph = getPosthog();
    // Reading opt-out state from PostHog is exactly the "synchronize with an
    // external system" case the rule's own guidance allows; it can't be a
    // lazy useState initialiser because the CDN snippet installs a stub whose
    // has_opted_out_capturing returns undefined until the real library loads.
    // null while unknown: rendering "on" before then would show a state the
    // user never chose.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOptedOut(ph?.has_opted_out_capturing?.() ?? null);
  }, []);

  const toggle = () => {
    const ph = getPosthog();
    if (!ph) return;
    if (optedOut) {
      ph.opt_in_capturing?.();
      setOptedOut(false);
      // Only measurable in this direction — an opt-out cannot report itself.
      track("analytics_opt_in", { surface: "privacy_page" });
    } else {
      // Fire before opting out, or the event never leaves.
      track("analytics_opt_out", { surface: "privacy_page" });
      ph.opt_out_capturing?.();
      setOptedOut(true);
    }
  };

  if (optedOut === null) {
    return (
      <p className="analytics-optout-status">
        Analytics status unavailable in this browser.
      </p>
    );
  }

  return (
    <div className="analytics-optout">
      <button
        type="button"
        className="btn-secondary"
        onClick={toggle}
        aria-pressed={optedOut}
      >
        {optedOut ? "Turn analytics back on" : "Turn analytics off"}
      </button>
      <span className="analytics-optout-status" role="status">
        {optedOut
          ? "Analytics and session replay are off for this browser."
          : "Analytics and session replay are on for this browser."}
      </span>
    </div>
  );
}
