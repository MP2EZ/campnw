import { useEffect, useState } from "react";
import { getPollStatus } from "../api";
import type { PollStatus } from "../api";

// ---------------------------------------------------------------------------
// Relative time helper — no external dependency
// ---------------------------------------------------------------------------

function relativeTime(isoString: string | null): string {
  if (!isoString) return "never";
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const diffSec = Math.round(diffMs / 1000);

  if (diffSec < 0) {
    // future
    const absSec = Math.abs(diffSec);
    if (absSec < 60) return `in ${absSec}s`;
    if (absSec < 3600) return `in ${Math.round(absSec / 60)}m`;
    return `in ${Math.round(absSec / 3600)}h`;
  }

  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`;
  return `${Math.round(diffSec / 86400)}d ago`;
}

function futureRelative(isoString: string | null): string {
  if (!isoString) return "—";
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = then - now;
  const diffSec = Math.round(diffMs / 1000);

  if (diffSec <= 0) return "now";
  if (diffSec < 60) return `in ${diffSec}s`;
  if (diffSec < 3600) return `in ${Math.round(diffSec / 60)}m`;
  return `in ${Math.round(diffSec / 3600)}h`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PollDashboard({ open }: { open: boolean }) {
  const [status, setStatus] = useState<PollStatus | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;

    const load = async () => {
      setLoading(true);
      const data = await getPollStatus();
      if (!cancelled) {
        setStatus(data);
        setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (loading && !status) {
    return (
      <div className="poll-dashboard poll-dashboard--loading">
        <p className="poll-dashboard-placeholder">Loading poll status...</p>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="poll-dashboard">
      <h3 className="poll-dashboard-heading">Poll status</h3>

      <div className="poll-dashboard-stats">
        <div className="poll-stat">
          <span className="poll-stat-label">Last poll</span>
          <span className="poll-stat-value">
            {relativeTime(status.last_poll)}
          </span>
        </div>
        <div className="poll-stat">
          <span className="poll-stat-label">Next poll</span>
          <span className="poll-stat-value">
            {futureRelative(status.next_poll)}
          </span>
        </div>
        <div className="poll-stat">
          <span className="poll-stat-label">Active watches</span>
          <span className="poll-stat-value">{status.active_watches}</span>
        </div>
        {status.last_errors > 0 && (
          <div className="poll-stat poll-stat--error">
            <span className="poll-stat-label">Errors</span>
            <span className="poll-stat-value">{status.last_errors}</span>
          </div>
        )}
      </div>

      {status.recent_notifications.length > 0 && (
        <div className="poll-notifications">
          <h4 className="poll-notifications-heading">Recent alerts</h4>
          <ul className="poll-notification-list">
            {status.recent_notifications.slice(0, 5).map((n, i) => (
              <li key={i} className="poll-notification-item">
                <div className="poll-notification-main">
                  <span className="poll-notification-name">{n.watch_name}</span>
                  <span
                    className={`poll-notification-status poll-notification-status--${n.status}`}
                  >
                    {n.status}
                  </span>
                </div>
                <div className="poll-notification-meta">
                  {n.changes_count} change{n.changes_count !== 1 ? "s" : ""}
                  {" · "}
                  {n.channel}
                  {" · "}
                  {relativeTime(n.sent_at)}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {status.recent_notifications.length === 0 && status.last_poll && (
        <p className="poll-no-notifications">No alerts sent yet.</p>
      )}
    </div>
  );
}
