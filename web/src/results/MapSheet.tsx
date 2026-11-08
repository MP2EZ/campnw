import "./mapSheet.css";
import { lazy, Suspense, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { CampgroundResult } from "../api";
import { IconClose, IconMap } from "../icons";
import type { SelectionStore } from "./selection";

// Leaflet comes with this chunk: a phone fetches it when the sheet first opens.
const ResultsMap = lazy(() => import("./ResultsMap"));

interface Props {
  places: CampgroundResult[];
  searchKey: unknown;
  selection: SelectionStore;
  /** A pin was chosen: the sheet has closed, so the page can show its card. */
  onSelect: (facilityId: string) => void;
}

const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/**
 * The results map on phones and tablets (D10): a "Map" button that opens a
 * bottom sheet. The sheet is a CSS scroll-snap scroller: dragging it snaps to
 * half height, full height or closed, with no gesture code. The handle is a
 * real button (half ↔ full) and Close and Escape work from the keyboard. The
 * map mounts only while the sheet is open.
 */
export function MapSheet({ places, searchKey, selection, onSelect }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const half = useRef<HTMLSpanElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const mapBox = useRef<HTMLDivElement>(null);
  // The sheet has risen since opening, so scrolling back to 0 means dragged shut.
  const risen = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const settle = useRef<ReturnType<typeof setTimeout>>(undefined);

  const offsets = () => ({
    half: (half.current?.offsetTop ?? 0) + 1,
    full: panel.current?.offsetHeight ?? 0,
  });
  const scrollTo = (top: number) => {
    const el = scroller.current;
    if (!el) return;
    if (el.scrollTo) el.scrollTo({ top, behavior: reducedMotion() ? "auto" : "smooth" });
    else el.scrollTop = top;
  };
  // Fit the map to the part of the sheet on screen, so a fit shows every pin.
  const fitMap = (visible: number) => {
    const pad = panel.current ? parseFloat(getComputedStyle(panel.current).paddingBottom) || 0 : 0;
    const h = Math.max(160, visible - (head.current?.offsetHeight ?? 0) - pad);
    if (mapBox.current) mapBox.current.style.height = `${h}px`;
  };

  const finish = useCallback((returnFocus: boolean) => {
    clearTimeout(timer.current);
    clearTimeout(settle.current);
    risen.current = false;
    setOpen(false);
    setFull(false);
    if (returnFocus) launcher.current?.focus();
  }, []);

  const close = useCallback(() => {
    const el = scroller.current;
    if (!el?.scrollTo || reducedMotion() || el.scrollTop < 4) return finish(true);
    el.scrollTo({ top: 0, behavior: "smooth" });
    timer.current = setTimeout(() => finish(true), 450);
  }, [finish]);

  // Open: start shut (scrollTop 0), focus the handle without scrolling to
  // it, then rise to half height.
  useLayoutEffect(() => {
    if (!open) return;
    fitMap(offsets().half);
    panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus({ preventScroll: true });
    const raf = requestAnimationFrame(() => scrollTo(offsets().half));
    return () => cancelAnimationFrame(raf);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
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
  }, [open, close]);
  useEffect(() => () => { clearTimeout(timer.current); clearTimeout(settle.current); }, []);

  // When a drag settles on a snap point: note full height, resize the map.
  const onScroll = () => {
    const y = scroller.current?.scrollTop ?? 0;
    if (y > 8) risen.current = true;
    else if (risen.current && y < 4) return finish(panel.current?.contains(document.activeElement) ?? false);
    clearTimeout(settle.current);
    settle.current = setTimeout(() => {
      setFull(y >= offsets().full - 8);
      fitMap(y);
    }, 120);
  };

  if (!places.some((r) => r.latitude && r.longitude)) return null;

  return (
    <>
      <div className="rv2-sheet-launch-wrap">
        <button ref={launcher} type="button" className="rv2-sheet-launch" aria-haspopup="dialog" aria-expanded={open}
          onClick={() => setOpen(true)}>
          <IconMap className="icon" /> Map
        </button>
      </div>
      {open && (
        <div ref={scroller} className="rv2-sheet" onScroll={onScroll}>
          <div className="rv2-sheet-spacer" aria-hidden="true" onClick={close} />
          <div ref={panel} className="rv2-sheet-panel" role="dialog" aria-modal="true" aria-labelledby={`${id}-h`}>
            <span ref={half} className="rv2-sheet-half" aria-hidden="true" />
            <div ref={head} className="rv2-sheet-head">
              <h2 id={`${id}-h`} className="rv2-sheet-title">Map of results</h2>
              <button type="button" className="rv2-sheet-handle" aria-label="Expand map" aria-expanded={full}
                data-autofocus onClick={() => {
                  const next = !full;
                  setFull(next);
                  const o = offsets();
                  fitMap(next ? o.full : o.half);
                  scrollTo(next ? o.full : o.half);
                }}>
                <span className="rv2-sheet-grip" aria-hidden="true" />
              </button>
              <button type="button" className="rv2-sheet-close" aria-label="Close map" onClick={close}>
                <IconClose className="icon" />
              </button>
              <p className="sr-only">The list has the same places.</p>
            </div>
            <div ref={mapBox} className="rv2-sheet-map">
              <Suspense fallback={<div className="rv2-map-loading" />}>
                <ResultsMap places={places} searchKey={searchKey} selection={selection}
                  onSelect={(fid) => { finish(false); onSelect(fid); }} />
              </Suspense>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
