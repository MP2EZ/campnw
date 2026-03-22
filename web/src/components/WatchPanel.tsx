import { useCallback, useEffect, useRef, useState } from "react";
import { getWatches, deleteWatch, toggleWatch, createWatch } from "../api";
import type { WatchData, CreateWatchParams } from "../api";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function WatchPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [watches, setWatches] = useState<WatchData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWatches();
      setWatches(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watches");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const handleDelete = async (id: number) => {
    await deleteWatch(id);
    setWatches((prev) => prev.filter((w) => w.id !== id));
  };

  const handleToggle = async (id: number) => {
    const result = await toggleWatch(id);
    setWatches((prev) =>
      prev.map((w) => (w.id === id ? { ...w, enabled: result.enabled } : w))
    );
  };

  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Focus trap: move focus into panel on open, return on close
  useEffect(() => {
    if (open && closeRef.current) {
      closeRef.current.focus();
    }
  }, [open]);

  // Trap focus inside panel
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="watch-overlay" onClick={onClose}>
      <div
        className="watch-panel"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="watch-panel-title"
      >
        <div className="watch-panel-header">
          <h2 id="watch-panel-title">Watchlist</h2>
          <button className="watch-close" onClick={onClose} ref={closeRef}>
            &times;
          </button>
        </div>

        {loading && <p className="watch-loading">Loading...</p>}
        {error && <p className="watch-error">{error}</p>}

        {!loading && watches.length === 0 && (
          <div className="watch-empty">
            <p>No active watches.</p>
            <p className="watch-hint">
              Search for a campground, then click "Watch" to get notified when
              sites open up.
            </p>
          </div>
        )}

        <div className="watch-list">
          {watches.map((w) => (
            <div
              key={w.id}
              className={`watch-item ${!w.enabled ? "paused" : ""}`}
            >
              <div className="watch-item-info">
                <h3>{w.name}</h3>
                <p className="watch-dates">
                  {w.start_date} → {w.end_date} · {w.min_nights}n min
                </p>
                {w.days_of_week && (
                  <p className="watch-days">
                    {w.days_of_week.map((d) => DAY_NAMES[d]).join(", ")}
                  </p>
                )}
                {!w.enabled && (
                  <span className="watch-paused-badge">Paused</span>
                )}
              </div>
              <div className="watch-item-actions">
                <button
                  className="watch-action-btn"
                  onClick={() => handleToggle(w.id)}
                  title={w.enabled ? "Pause" : "Resume"}
                >
                  {w.enabled ? "⏸" : "▶"}
                </button>
                <button
                  className="watch-action-btn watch-delete"
                  onClick={() => handleDelete(w.id)}
                  title="Delete"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function WatchButton({
  facilityId,
  name,
  startDate,
  endDate,
  minNights,
  daysOfWeek,
  onCreated,
}: {
  facilityId: string;
  name: string;
  startDate: string;
  endDate: string;
  minNights?: number;
  daysOfWeek?: number[];
  onCreated?: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(false);

  const handleWatch = async () => {
    setCreating(true);
    try {
      const params: CreateWatchParams = {
        facility_id: facilityId,
        name,
        start_date: startDate,
        end_date: endDate,
        min_nights: minNights || 1,
        days_of_week: daysOfWeek,
      };
      await createWatch(params);
      setCreated(true);
      onCreated?.();
      setTimeout(() => setCreated(false), 3000);
    } catch {
      // ignore
    } finally {
      setCreating(false);
    }
  };

  if (created) {
    return <span className="watch-created">Watching ✓</span>;
  }

  return (
    <button
      className="watch-cta-btn"
      onClick={handleWatch}
      disabled={creating}
    >
      {creating ? "..." : "Watch"}
    </button>
  );
}
