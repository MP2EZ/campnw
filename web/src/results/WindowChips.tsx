import { useState } from "react";
import type { SearchParams } from "../api";
import { chipCountText, type WindowChip, type WindowChips as Chips } from "./chips";

interface Props {
  chips: Chips;
  name: string;
  params: SearchParams | null;
  /** An open chip was pressed: show its sites (P3b). `el` gets focus back. */
  onOpen: (chip: WindowChip, el: HTMLElement) => void;
  /** A full chip opens the Watch sheet (P3c); without this it only says "Full". */
  onWatch?: (chip: WindowChip) => void;
  /** A not-released chip whose start is in `remindStarts` opens a release reminder (P3d). */
  onRemind?: (chip: WindowChip) => void;
  remindStarts?: ReadonlySet<string>;
}

function groupLabel(params: SearchParams | null): string {
  if (params?.mode === "exact") return "Your dates";
  const days = (params?.days_of_week ?? "").split(",").filter(Boolean).map(Number).sort().join(",");
  if (days === "4,5,6" || days === "3,4,5,6") return "Weekends";
  return days && days !== "0,1,2,3,4,5,6" ? "Open dates" : `${params?.nights ?? 2}-night stays`;
}

/**
 * The stays a card offers. An open chip opens the site panel (P3b), which
 * hands off to the booking site. "Few" is said in words ("3 left") and marked
 * with a dot, never by colour alone.
 */
export function WindowChips({ chips, name, params, onOpen, onWatch, onRemind, remindStarts }: Props) {
  const [all, setAll] = useState(false);
  const list = all ? [...chips.shown, ...chips.more] : chips.shown;

  return (
    <div role="group" aria-label={`${groupLabel(params)} at ${name}`} className="rv2-chips">
      {list.map((c) => {
        const watch = c.status === "full" && !!onWatch;
        const remind = c.status === "not_released" && !!onRemind && !!remindStarts?.has(c.start);
        const body = (
          <>
            <span className="rv2-chip-dates">{c.label}</span>
            {/* The comma alone: accessible names trim a hidden ", ". Flex drops the space visually. */}
            <span className="sr-only">,</span>{" "}
            <span className="rv2-chip-count">
              {c.few && <span className="rv2-chip-dot" aria-hidden="true" />}
              {chipCountText(c)}{watch && " · Watch"}{remind && " · Remind me"}
            </span>
          </>
        );
        const key = `${c.start}→${c.end}`;
        if (watch) {
          return (
            <button key={key} type="button" className="rv2-chip rv2-chip-full rv2-chip-watch" onClick={() => onWatch(c)}>
              {body}
            </button>
          );
        }
        if (remind) {
          return (
            <button key={key} type="button" className="rv2-chip rv2-chip-full rv2-chip-watch" onClick={() => onRemind(c)}>
              {body}
            </button>
          );
        }
        if (c.status !== "open") {
          // Not reservable, or no release date to remind on: this only says what's there.
          return <span key={key} className="rv2-chip rv2-chip-full">{body}</span>;
        }
        return (
          <button key={key} type="button" className="rv2-chip" aria-haspopup="dialog"
            onClick={(e) => onOpen(c, e.currentTarget)}>
            {body}
            <span className="sr-only">, see open sites</span>
          </button>
        );
      })}
      {chips.more.length > 0 && (
        <button type="button" className="rv2-chip-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `+${chips.more.length} more`}
        </button>
      )}
    </div>
  );
}
