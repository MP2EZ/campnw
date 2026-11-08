import { useCallback, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { track, type SearchParams } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { useSearchContext } from "../contexts/SearchContext";
import { IconSearch } from "../icons";
import {
  barToParams, compactLabel, DEFAULT_BAR, driveLabel, paramsToBar, whenLabel, whereLabel, whoLabel,
  type BarState,
} from "./searchState";
import { DrivePanel, WhenPanel, WhoPanel, type PanelProps } from "./SearchPanels";
import { WherePanel } from "./WherePanel";

interface Props {
  onSearch: (params: SearchParams, mode: SearchMode) => void;
  /** A plain-language search, through the existing NL path. */
  onAsk: (query: string) => void;
  /** The signed-in user's drive-from and nights, before there's a search. */
  userDefaults?: { from?: string; nights?: number };
}

type SegmentKey = "where" | "when" | "who" | "drive";
const SEGMENTS: Array<{ key: SegmentKey; title: string; label: (b: BarState) => string; Panel: (p: PanelProps) => ReactNode }> = [
  { key: "where", title: "Where", label: whereLabel, Panel: WherePanel },
  { key: "when", title: "When", label: whenLabel, Panel: WhenPanel },
  { key: "who", title: "Who", label: whoLabel, Panel: WhoPanel },
  { key: "drive", title: "Drive", label: driveLabel, Panel: DrivePanel },
];

function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Focus and dismissal for a popover or sheet: focus moves in on open, Escape
 * closes and returns focus to the trigger, a pointer outside closes. A modal
 * sheet also keeps Tab inside.
 */
function useDialogFocus(
  ref: RefObject<HTMLElement | null>,
  trigger: RefObject<HTMLElement | null>,
  open: boolean,
  close: () => void,
  modal = false,
) {
  useEffect(() => {
    if (!open) return;
    const el = ref.current;
    (el?.querySelector<HTMLElement>("[data-autofocus]") ?? el?.querySelector<HTMLElement>(FOCUSABLE))?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        trigger.current?.focus();
      } else if (modal && e.key === "Tab" && el) {
        const all = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)];
        const first = all[0];
        const last = all[all.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!el?.contains(t) && !trigger.current?.contains(t)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close, modal, ref, trigger]);
}

function Segment({ seg, bar, open, onToggle, onClose, panelProps }: {
  seg: (typeof SEGMENTS)[number]; bar: BarState; open: boolean;
  onToggle: () => void; onClose: () => void; panelProps: PanelProps;
}) {
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useDialogFocus(pop, btn, open, onClose);
  const { Panel } = seg;
  return (
    <div className={`sb-seg sb-seg-${seg.key}`}>
      <button ref={btn} type="button" className="sb-seg-btn" aria-haspopup="dialog"
        aria-expanded={open} aria-controls={open ? `${id}-pop` : undefined} onClick={onToggle}>
        <span className="sb-seg-title">{seg.title}</span>
        <span className="sb-seg-value">{seg.label(bar)}</span>
      </button>
      {open && (
        <div ref={pop} id={`${id}-pop`} className="sb-pop" role="dialog" aria-labelledby={`${id}-h`}>
          <h2 id={`${id}-h`} className="sb-pop-title">{seg.title}</h2>
          <Panel {...panelProps} />
          <div className="sb-pop-foot">
            <button type="button" className="sb-done" onClick={() => { onClose(); btn.current?.focus(); }}>Done</button>
            <button type="submit" className="sb-go">Search</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The mobile bar: one button that opens every segment in a sheet. */
function CompactBar({ bar, panelProps, open, onOpen, close }: {
  bar: BarState; panelProps: PanelProps; open: boolean; onOpen: () => void; close: () => void;
}) {
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  useDialogFocus(sheet, btn, open, close, true);
  const { title, detail } = compactLabel(bar);
  return (
    <div className="sb-compact">
      <button ref={btn} type="button" className="sb-compact-btn" aria-haspopup="dialog" aria-expanded={open}
        aria-label={`Edit search: ${title}, ${detail}`} onClick={onOpen}>
        <span className="sb-compact-title">{title}</span>
        <span className="sb-compact-detail">{detail}</span>
      </button>
      <button type="submit" className="sb-submit" aria-label="Search"><IconSearch className="icon" /></button>
      {open && (
        <div className="sb-sheet-scrim">
          <div ref={sheet} className="sb-sheet" role="dialog" aria-modal="true" aria-labelledby={`${id}-h`}>
            <div className="sb-sheet-head">
              <h2 id={`${id}-h`} className="sb-pop-title">Edit search</h2>
              <button type="button" className="sb-done" onClick={() => { close(); btn.current?.focus(); }}>Close</button>
            </div>
            {SEGMENTS.map(({ key, title: t, Panel }) => (
              <section key={key} className="sb-sheet-section" aria-label={t}>
                <h3 className="sb-sheet-h">{t}</h3>
                <Panel {...panelProps} />
              </section>
            ))}
            <div className="sb-sheet-foot">
              <button type="submit" className="sb-go">Search</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AskForm({ onAsk }: { onAsk: (q: string) => void }) {
  const [value, setValue] = useState("");
  const id = useId();
  return (
    <form className="sb-ask" role="search" aria-label="Ask in plain language"
      onSubmit={(e) => {
        e.preventDefault();
        const q = value.trim();
        if (!q) return;
        onAsk(q);
        setValue("");
      }}>
      <label htmlFor={id} className="sb-ask-label">Or ask</label>
      <input id={id} className="sb-ask-input" type="text" value={value} onChange={(e) => setValue(e.target.value)}
        placeholder="pet-friendly near Portland, a July weekend" />
      <button type="submit" className="sb-ask-go" disabled={!value.trim()}>Ask</button>
    </form>
  );
}

/**
 * The v2 search bar (v1.48 P3a): Where / When / Who / Drive segments over a
 * draft of the search, with a popover each on desktop and one sheet on
 * mobile. It shows the current search, and follows it when a new one runs
 * (Back, a shared link, or what a plain-language question was parsed into).
 */
export default function SearchBar({ onSearch, onAsk, userDefaults }: Props) {
  const { searchParams } = useSearchContext();
  const today = localToday();
  const fromSearch = useCallback(
    (p: SearchParams | null): BarState => p ? paramsToBar(p, today) : {
      ...DEFAULT_BAR,
      from: userDefaults?.from || DEFAULT_BAR.from,
      nights: userDefaults?.nights || DEFAULT_BAR.nights,
    },
    [today, userDefaults?.from, userDefaults?.nights],
  );
  const [bar, setBar] = useState(() => fromSearch(searchParams));
  const [synced, setSynced] = useState({ searchParams, fromSearch });
  if (synced.searchParams !== searchParams || (!searchParams && synced.fromSearch !== fromSearch)) {
    setSynced({ searchParams, fromSearch });
    setBar(fromSearch(searchParams));
  }
  // One of the four popovers, or the mobile sheet.
  const [open, setOpen] = useState<SegmentKey | "sheet" | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const panelProps: PanelProps = { bar, onChange: setBar, today };

  return (
    <div className="sb-wrap">
      <form className="sb" role="search" aria-label="Campsite search"
        onSubmit={(e) => {
          e.preventDefault();
          setOpen(null);
          const params = barToParams(bar, today, searchParams);
          track("search_bar_submitted", { when: bar.when.kind, where: bar.name ? "name" : "drive" });
          onSearch(params, params.mode === "exact" ? "exact" : "find");
        }}>
        <div className="sb-segments">
          {SEGMENTS.map((seg, i) => (
            <div key={seg.key} className="sb-seg-slot">
              {i > 0 && <span className="sb-divider" aria-hidden="true" />}
              <Segment seg={seg} bar={bar} open={open === seg.key}
                onToggle={() => setOpen(open === seg.key ? null : seg.key)} onClose={close} panelProps={panelProps} />
            </div>
          ))}
          <button type="submit" className="sb-submit" aria-label="Search"><IconSearch className="icon" /></button>
        </div>
        <CompactBar bar={bar} panelProps={panelProps} open={open === "sheet"} onOpen={() => setOpen("sheet")} close={close} />
      </form>
      <AskForm onAsk={onAsk} />
    </div>
  );
}
