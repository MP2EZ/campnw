import "./sitePanel.css";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CampgroundResult, SearchParams } from "../api";
import { formatDriveTime, parseIsoDate } from "../lib/dates";
import { IconClose, IconExternal } from "../icons";
import { FEW_LEFT, type WindowChip } from "./chips";
import { BOOKING_SITES, handoffCopy, stayLabel } from "./handoff";
import { panelGroups, type PanelSite } from "./siteGroups";

interface Props {
  result: CampgroundResult;
  chip: Pick<WindowChip, "start" | "end">;
  params: SearchParams | null;
  /** Gets focus back when the panel closes: the chip that opened it. */
  returnFocus: HTMLElement | null;
  onClose: () => void;
  onBook: (site: PanelSite, sites: number) => void;
}

const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]):checked, input:not([type="radio"]):not([disabled])';
const weekday = (iso: string) => parseIsoDate(iso).toLocaleDateString("en-US", { weekday: "short" });

function partText({ start, end }: { start: string; end: string }): string {
  return start === end ? `${weekday(start)} night only` : `${weekday(start)}–${weekday(end)} nights only`;
}

/**
 * The open sites behind one chip (v1.48 P3b): a modal dialog, a side panel
 * on wide screens and a bottom sheet on phones. Pick a site, then "Book on
 * <booking site>" opens that site's page in a new tab; the copy under the
 * button says what that site fills in.
 */
export function SitePanel({ result, chip, params, returnFocus, onClose, onBook }: Props) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  // Read through refs so a parent's new callback doesn't re-run the mount effect.
  const close = useRef(onClose);
  const opener = useRef(returnFocus);
  useEffect(() => { close.current = onClose; }, [onClose]);
  const groups = useMemo(() => panelGroups(result, chip, params), [result, chip, params]);
  const sites = groups.flatMap((g) => g.sites);
  const [chosen, setChosen] = useState(sites[0]?.id);
  const site = sites.find((s) => s.id === chosen) ?? sites[0];
  const where = BOOKING_SITES[result.booking_system] ?? result.booking_system;
  const meta = [
    result.boat_in ? "Boat-in only" : result.estimated_drive_minutes != null
      ? `${formatDriveTime(result.estimated_drive_minutes)} drive` : null,
    result.region,
  ].filter(Boolean).join(" · ");

  useEffect(() => {
    const back = opener.current;
    panel.current?.focus({ preventScroll: true });
    const root = document.getElementById("root");
    const page = root && !root.contains(panel.current) ? root : null;
    page?.setAttribute("inert", "");
    const overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      } else if (e.key === "Tab" && panel.current) {
        const all = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
        const first = all[0];
        const last = all[all.length - 1];
        const at = document.activeElement;
        if (e.shiftKey && (at === first || at === panel.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && at === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      page?.removeAttribute("inert");
      document.documentElement.style.overflow = overflow;
      back?.focus({ preventScroll: true });
    };
  }, []);

  const count = sites.length;
  const few = count <= FEW_LEFT;

  return createPortal(
    <div className="rv2-panel-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} className="rv2-panel" role="dialog" aria-modal="true" aria-labelledby={`${id}-h`} tabIndex={-1}>
        <div className="rv2-panel-head">
          <div className="rv2-panel-titles">
            <h2 id={`${id}-h`} className="rv2-panel-title">{result.name}</h2>
            <p className="rv2-panel-stay">{stayLabel(chip.start, chip.end)}</p>
            {meta && <p className="rv2-panel-meta">{meta}</p>}
          </div>
          <button type="button" className="rv2-panel-close" aria-label="Close" onClick={onClose}>
            <IconClose className="icon" />
          </button>
        </div>

        <div className="rv2-panel-body">
          <p className={few ? "rv2-panel-count is-few" : "rv2-panel-count"}>
            {few && <span className="rv2-chip-dot" aria-hidden="true" />}
            <span><strong>{count} site{count === 1 ? "" : "s"} {few ? "left" : "open"}</strong> for these nights. Pick one to book.</span>
          </p>
          {groups.map((g) => (
            <fieldset key={g.kind} className="rv2-panel-group">
              <legend className="rv2-panel-legend">
                <span className="rv2-panel-group-title">{g.title}</span>
                <span className="sr-only">,</span>{" "}
                <span className="rv2-panel-group-count">{g.sites.length} open</span>
              </legend>
              {g.sites.map((s) => {
                const detail = [s.loop, s.people != null && `up to ${s.people} people`,
                  s.part && partText(s.part)].filter(Boolean).join(" · ");
                const listed = s.kind !== "unlisted";
                return (
                  <label key={s.id} className="rv2-site">
                    <input type="radio" name={`${id}-site`} value={s.id} checked={site?.id === s.id}
                      onChange={() => setChosen(s.id)} />
                    <span className="rv2-site-name"><span className="sr-only">Site</span>{" "}{s.name}</span>
                    {/* Unlisted sites sit under a legend that says so; the row doesn't repeat it. */}
                    {(listed || detail) && <><span className="sr-only">,</span>{" "}</>}
                    <span className="rv2-site-main">
                      {listed && <span className="rv2-site-fit">{s.fit}</span>}
                      {listed && detail && <><span className="sr-only">,</span>{" "}</>}
                      {detail && <span className="rv2-site-detail">{detail}</span>}
                    </span>
                    {(s.hookups || s.walkIn) && (
                      <span className="rv2-site-tags">
                        {s.hookups && <><span className="sr-only">,</span>{" "}<span className="rv2-site-tag">Hookups</span></>}
                        {s.walkIn && <><span className="sr-only">,</span>{" "}<span className="rv2-site-tag">Walk-in</span></>}
                      </span>
                    )}
                  </label>
                );
              })}
            </fieldset>
          ))}
          {count > 0 && <p className="rv2-panel-source">Site details come from {where}. Pad size and shade aren’t listed.</p>}
        </div>

        <div className="rv2-panel-foot">
          {site?.href ? (
            <a className="rv2-panel-book" href={site.href} target="_blank" rel="noopener"
              onClick={() => onBook(site, count)}>
              Book on {where}<IconExternal className="icon" />
              <span className="sr-only">, site {site.name} (opens in a new tab)</span>
            </a>
          ) : (
            <p className="rv2-panel-handoff">{where} has no booking link for these nights.</p>
          )}
          {site?.href && <p className="rv2-panel-handoff">{handoffCopy(result.booking_system, site)}</p>}
        </div>
      </div>
    </div>,
    document.body,
  );
}
