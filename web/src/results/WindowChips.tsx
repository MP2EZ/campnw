import { useState } from "react";
import type { SearchParams } from "../api";
import { chipCountText, type WindowChip, type WindowChips as Chips } from "./chips";

interface Props {
  chips: Chips;
  name: string;
  params: SearchParams | null;
  /** "WA State Parks": where the chip hands off to. */
  source: string;
  onBook: (chip: WindowChip) => void;
  /** A full chip opens the Watch sheet (P3c); without this it only says "Full". */
  onWatch?: (chip: WindowChip) => void;
}

function groupLabel(params: SearchParams | null): string {
  if (params?.mode === "exact") return "Your dates";
  const days = (params?.days_of_week ?? "").split(",").filter(Boolean).map(Number).sort().join(",");
  if (days === "4,5,6" || days === "3,4,5,6") return "Weekends";
  return days && days !== "0,1,2,3,4,5,6" ? "Open dates" : `${params?.nights ?? 2}-night stays`;
}

/**
 * The stays a card offers. Each chip hands off to the booking site until the
 * site panel (P3b) opens instead. "Few" is said in words ("3 left") and marked
 * with a dot, never by colour alone.
 */
export function WindowChips({ chips, name, params, source, onBook, onWatch }: Props) {
  const [all, setAll] = useState(false);
  const list = all ? [...chips.shown, ...chips.more] : chips.shown;

  return (
    <div role="group" aria-label={`${groupLabel(params)} at ${name}`} className="rv2-chips">
      {list.map((c) => {
        const watch = c.status === "full" && !!onWatch;
        const body = (
          <>
            <span className="rv2-chip-dates">{c.label}</span>
            {/* The comma alone: accessible names trim a hidden ", ". Flex drops the space visually. */}
            <span className="sr-only">,</span>{" "}
            <span className="rv2-chip-count">
              {c.few && <span className="rv2-chip-dot" aria-hidden="true" />}
              {chipCountText(c)}{watch && " · Watch"}
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
        if (c.status !== "open") {
          // Remind me (not released) arrives with P3d; until then this only says what's there.
          return <span key={key} className="rv2-chip rv2-chip-full">{body}</span>;
        }
        return c.href ? (
          <a key={key} className="rv2-chip" href={c.href} target="_blank" rel="noopener" onClick={() => onBook(c)}>
            {body}
            <span className="sr-only">, book on {source} (opens in a new tab)</span>
          </a>
        ) : (
          <span key={key} className="rv2-chip">{body}</span>
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
