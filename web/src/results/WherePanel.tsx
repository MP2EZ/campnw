import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { findCampgrounds, type CampgroundMatch } from "../api";
import { SOURCE_NAMES } from "../lib/sources";
import { FromSelect, type PanelProps } from "./SearchPanels";

const DEBOUNCE_MS = 250;

/**
 * Campground-name typeahead (ARIA 1.2 combobox with a listbox popup). The
 * text is the name filter as typed, so Search with no option picked still
 * matches every campground whose name contains it; picking an option fills in
 * the full name.
 */
export function CampgroundCombobox({ value, onChange, inputRef }: {
  value: string; onChange: (name: string) => void; inputRef?: RefObject<HTMLInputElement | null>;
}) {
  const id = useId();
  const listId = `${id}-list`;
  const [matches, setMatches] = useState<CampgroundMatch[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState<string | null>(null);

  useEffect(() => {
    const q = query?.trim() ?? "";
    if (q.length < 2) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      findCampgrounds(q, ctl.signal)
        .then((found) => {
          setMatches(found);
          setActive(-1);
          setExpanded(found.length > 0);
          setStatus(found.length ? `${found.length} campground${found.length === 1 ? "" : "s"} found` : "No campgrounds match");
        })
        .catch(() => {});
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [query]);

  const pick = (m: CampgroundMatch) => {
    onChange(m.name);
    setExpanded(false);
    setActive(-1);
    setQuery(null);
    setStatus(`${m.name} selected`);
  };

  return (
    <div className="sb-field sb-combo">
      <label htmlFor={id} className="sb-field-label">Or a campground by name</label>
      <input
        ref={inputRef}
        id={id}
        className="sb-input"
        type="text"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded && active >= 0 ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        placeholder="e.g. Ohanapecosh"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setQuery(e.target.value);
          if (e.target.value.trim().length < 2) { setExpanded(false); setMatches([]); setStatus(""); }
        }}
        onBlur={() => setExpanded(false)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            if (!matches.length) return;
            e.preventDefault();
            const step = e.key === "ArrowDown" ? 1 : -1;
            setExpanded(true);
            setActive((a) => (expanded ? (a + step + matches.length) % matches.length : step > 0 ? 0 : matches.length - 1));
          } else if (e.key === "Enter" && expanded && active >= 0) {
            e.preventDefault();
            pick(matches[active]);
          } else if (e.key === "Escape" && expanded) {
            e.preventDefault();
            e.stopPropagation();
            setExpanded(false);
            setActive(-1);
          }
        }}
      />
      <ul id={listId} role="listbox" aria-label="Campgrounds" className="sb-options" hidden={!expanded}>
        {matches.map((m, i) => (
          <li
            key={m.facility_id}
            id={`${id}-opt-${i}`}
            role="option"
            aria-selected={i === active}
            className="sb-option"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => pick(m)}
          >
            <span className="sb-option-name">{m.name}</span>
            <span className="sb-option-meta">{[m.region || m.state, SOURCE_NAMES[m.booking_system]].filter(Boolean).join(" · ")}</span>
          </li>
        ))}
      </ul>
      <span className="sr-only" role="status" aria-live="polite">{status}</span>
    </div>
  );
}

export function WherePanel(props: PanelProps) {
  const { bar, onChange } = props;
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <FromSelect {...props} />
      <CampgroundCombobox value={bar.name} onChange={(name) => onChange({ ...bar, name })} inputRef={input} />
      {bar.name && (
        <div className="sb-name-row">
          <p className="sb-note">Searching by name ignores drive time.</p>
          <button type="button" className="sb-link" onClick={() => { onChange({ ...bar, name: "" }); input.current?.focus(); }}>
            Clear name
          </button>
        </div>
      )}
    </>
  );
}
