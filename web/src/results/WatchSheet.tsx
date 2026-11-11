import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createWatch, track, WatchLimitError, type CampgroundResult, type SearchParams } from "../api";
import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { IconClose } from "../icons";
import { UpgradeModal } from "../components/UpgradeModal";
import type { Equipment } from "./searchState";
import { hasFilters, watchRequest, whoFromParams, whoText, type WatchStay, type WatchWho } from "./watch";

export type WatchFrom = "chip" | "full_group";

interface Props {
  place: CampgroundResult;
  params: SearchParams | null;
  /** What can be watched here (watchStays); at least one. */
  stays: WatchStay[];
  /** The stay to start on (its first night). */
  initial?: string;
  from: WatchFrom;
  onClose: () => void;
  /** Open the sign-in modal. The sheet closes first. */
  onSignIn?: () => void;
}

const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]), select, [tabindex]:not([tabindex="-1"])';

function errorText(e: unknown, name: string): string {
  const msg = e instanceof Error ? e.message : "";
  if (msg.endsWith(": 409")) return `You're already watching ${name} for these dates.`;
  return "Couldn't start the watch. Check your connection and try again.";
}

/**
 * The Watch sheet (v1.48 P3c, D8): one watch for one full stay, with the
 * search's party and rig as site filters. A centred dialog on desktop, a
 * bottom sheet on phones (watchSheet.css).
 */
export function WatchSheet({ place, params, stays, initial, from, onClose, onSignIn }: Props) {
  const id = useId();
  const { user } = useAuth();
  const { isPro } = useBilling();
  const push = usePushNotifications();
  const panel = useRef<HTMLDivElement>(null);
  const [stayStart, setStayStart] = useState(initial ?? stays[0]?.start);
  const [who, setWho] = useState<WatchWho>(() => whoFromParams(params));
  const [editWho, setEditWho] = useState(false);
  const [hookups, setHookups] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [limit, setLimit] = useState<{ limit: number; current: number } | null>(null);
  const stay = stays.find((s) => s.start === stayStart) ?? stays[0];

  // Focus the title on open and on success; trap Tab; Escape closes; give
  // focus back to whatever opened the sheet.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, []);
  useEffect(() => {
    panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
  }, [done]);
  useEffect(() => {
    if (limit) return; // the upgrade modal has the keyboard
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Tab" && panel.current) {
        const all = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
        const first = all[0];
        const last = all[all.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, limit]);

  if (!stay) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!user) return;
    const req = watchRequest(place, stay, params, { who, hookups });
    setSaving(true);
    setError(null);
    try {
      await createWatch(req);
      track("watch_created", {
        from,
        has_filters: hasFilters(req) ? 1 : 0,
        ui_version: "v2",
        facility_id: place.facility_id,
        source: place.booking_system,
        start_date: req.start_date,
        end_date: req.end_date,
        min_nights: req.min_nights ?? 1,
        notification_channel: "web_push",
        push_already_granted: push.subscribed ? 1 : 0,
      });
      setDone(true);
    } catch (err) {
      if (err instanceof WatchLimitError) setLimit({ limit: err.limit, current: err.current });
      else setError(errorText(err, place.name));
    } finally {
      setSaving(false);
    }
  };

  const signIn = () => {
    onClose();
    onSignIn?.();
  };
  const setPeople = (v: string) => {
    const n = Number(v);
    setWho({ ...who, people: Number.isInteger(n) && n >= 1 && n <= 50 ? n : null });
  };
  const setRig = (v: string) => {
    const equipment = (v || null) as Equipment | null;
    setWho({ ...who, equipment, rigLength: equipment === "trailer" ? who.rigLength : null });
  };
  const setLength = (v: string) => {
    const n = Number(v);
    setWho({ ...who, rigLength: Number.isInteger(n) && n >= 1 && n <= 100 ? n : null });
  };

  const pushNote = !push.subscribed && (
    push.permission === "denied"
      ? <p className="rv2-watch-muted">Notifications are blocked for Campable in this browser. Allow them in its settings to get alerts.</p>
      : <button type="button" className="rv2-watch-secondary" onClick={() => void push.subscribe()}>Turn on notifications</button>
  );

  return (
    <>
      <div className="rv2-watch-backdrop" onClick={onClose} hidden={!!limit}>
        <div ref={panel} className="rv2-watch" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`}
          onClick={(e) => e.stopPropagation()}>
          <div className="rv2-watch-head">
            <div className="rv2-watch-heading">
              <h2 id={`${id}-title`} className="rv2-watch-title" tabIndex={-1} data-autofocus={done ? undefined : ""}>
                Watch {place.name}
              </h2>
              <p className="rv2-watch-muted">
                We check every {isPro ? 5 : 15} minutes and alert you when a site that fits you opens.
              </p>
            </div>
            <button type="button" className="rv2-watch-close" aria-label="Close" onClick={onClose}>
              <IconClose className="rv2-icon" />
            </button>
          </div>

          {done ? (
            <div className="rv2-watch-body">
              <p className="rv2-watch-done" tabIndex={-1} data-autofocus="">
                Watching {stay.label}. We'll alert you when a site opens.
              </p>
              {pushNote}
              <div className="rv2-watch-foot">
                <button type="button" className="rv2-watch-primary" onClick={onClose}>Done</button>
              </div>
            </div>
          ) : (
            <form className="rv2-watch-body" onSubmit={submit}>
              <fieldset className="rv2-watch-set">
                <legend className="rv2-watch-legend">Which dates?</legend>
                {stays.length === 1 ? (
                  <p className="rv2-watch-row">{stay.label} · Full now</p>
                ) : stays.map((s) => (
                  <label key={s.start} className="rv2-watch-option">
                    <input type="radio" name={`${id}-stay`} checked={s.start === stay.start}
                      onChange={() => setStayStart(s.start)} />
                    {s.label} <span className="rv2-watch-muted">· Full now</span>
                  </label>
                ))}
              </fieldset>

              <fieldset className="rv2-watch-set">
                <legend className="rv2-watch-legend">Which sites?</legend>
                <div className="rv2-watch-row">
                  <span>{whoText(who)}</span>
                  <button type="button" className="rv2-watch-link" aria-expanded={editWho}
                    aria-controls={`${id}-who`} aria-label="Change party and rig" onClick={() => setEditWho(!editWho)}>
                    Change
                  </button>
                </div>
                {editWho && (
                  <div id={`${id}-who`} className="rv2-watch-who">
                    <label className="rv2-watch-field">
                      People
                      <input type="number" min={1} max={50} inputMode="numeric" value={who.people ?? ""}
                        onChange={(e) => setPeople(e.target.value)} />
                    </label>
                    <label className="rv2-watch-field">
                      Rig
                      <select value={who.equipment ?? ""} onChange={(e) => setRig(e.target.value)}>
                        <option value="">Any</option>
                        <option value="tent">Tent</option>
                        <option value="van">Van</option>
                        <option value="trailer">Trailer or RV</option>
                      </select>
                    </label>
                    {who.equipment === "trailer" && (
                      <label className="rv2-watch-field">
                        Length (ft)
                        <input type="number" min={1} max={100} inputMode="numeric" value={who.rigLength ?? ""}
                          onChange={(e) => setLength(e.target.value)} />
                      </label>
                    )}
                  </div>
                )}
                <label className="rv2-watch-option">
                  <input type="radio" name={`${id}-sites`} checked={!hookups} onChange={() => setHookups(false)} />
                  Any site that fits
                </label>
                <label className="rv2-watch-option">
                  <input type="radio" name={`${id}-sites`} checked={hookups} onChange={() => setHookups(true)} />
                  Only sites with hookups
                </label>
                <p className="rv2-watch-muted">Sites that don't list their size or type still count, so you don't miss one.</p>
              </fieldset>

              <fieldset className="rv2-watch-set">
                <legend className="rv2-watch-legend">Alert me by</legend>
                <p className="rv2-watch-row">Push notification</p>
                {user && pushNote}
              </fieldset>

              {error && <p role="alert" className="rv2-watch-error">{error}</p>}

              <div className="rv2-watch-foot">
                {user ? (
                  <button type="submit" className="rv2-watch-primary" disabled={saving}>
                    {saving ? "Starting…" : `Start watching ${stay.label}`}
                  </button>
                ) : (
                  <>
                    <button type="button" className="rv2-watch-primary" onClick={signIn}>Sign in to watch</button>
                    <p className="rv2-watch-muted">Alerts need an account, so we know where to send them.</p>
                  </>
                )}
              </div>
            </form>
          )}
        </div>
      </div>
      <UpgradeModal open={!!limit} reason="watch_limit" contextInfo={limit ?? undefined}
        onClose={onClose} />
    </>
  );
}
