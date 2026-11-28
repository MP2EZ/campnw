import "../results/watchSheet.css";
import { useEffect, useRef } from "react";
import { track } from "../api";
import { IconClose } from "../icons";
import { providerLabel, type PushAlert } from "../lib/pushAlerts";

/** What a tapped watch alert opens: what was found, and one way to book it.
 * The link goes to the system browser so the user's provider login (and the
 * Recreation.gov app, if installed) is there. */
export function PushAlertSheet({
  alert,
  onClose,
  onOpenWatchlist,
}: {
  alert: PushAlert;
  onClose: () => void;
  onOpenWatchlist: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const provider = providerLabel(alert.bookingUrl);
  const book = () => {
    track("push_alert_book_clicked", { watch_id: alert.watchId });
    window.open(alert.bookingUrl, "_blank");
    onClose();
  };

  return (
    <div className="rv2-watch-backdrop" onClick={onClose}>
      <div className="rv2-watch" role="dialog" aria-modal="true" aria-labelledby="push-alert-title"
        onClick={(e) => e.stopPropagation()}>
        <div className="rv2-watch-head">
          <div className="rv2-watch-heading">
            <h2 id="push-alert-title" className="rv2-watch-title" tabIndex={-1} ref={heading}>
              {alert.title || "Sites opened up"}
            </h2>
            {alert.body && <p className="rv2-watch-muted">{alert.body}</p>}
          </div>
          <button type="button" className="rv2-watch-close" aria-label="Close" onClick={onClose}>
            <IconClose className="rv2-icon" />
          </button>
        </div>
        <div className="rv2-watch-body">
          <p className="rv2-watch-muted">Cancellations usually go within minutes.</p>
          <div className="rv2-watch-foot">
            <button type="button" className="rv2-watch-primary" onClick={book}>
              Book on {provider}
            </button>
            <button type="button" className="rv2-watch-secondary"
              onClick={() => { onClose(); onOpenWatchlist(); }}>
              See my watchlist
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
