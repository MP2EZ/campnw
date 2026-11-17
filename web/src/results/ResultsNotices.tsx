import type { SearchResponse } from "../api";
import { notReleasedMessage } from "../lib/notReleased";
import { IconCalendar } from "../icons";

/**
 * What the results can't show: nights not released yet (with when booking
 * opens) and booking systems that couldn't be checked. Both change how the
 * answer above should be read, so they sit directly under it.
 */
export function ResultsNotices({ results, withNotReleased = true, onCheckAgain }: {
  results: SearchResponse;
  /** False on the zero page, whose release timeline says it in full. */
  withNotReleased?: boolean;
  /**
   * Re-runs the same search. Offered on "still checking" (pending) warnings:
   * those campgrounds keep being checked after the search ends, and a repeat
   * gets them from the cache.
   */
  onCheckAgain?: () => void;
}) {
  const notReleased = withNotReleased ? notReleasedMessage(results) : null;
  const warnings = results.warnings ?? [];
  if (!notReleased && warnings.length === 0) return null;

  return (
    <div className="rv2-notices">
      {notReleased && (
        <div role="note" className="rv2-notice-info">
          <IconCalendar className="rv2-notice-icon" />
          <p>{notReleased}</p>
        </div>
      )}
      {warnings.map((w) => (
        <p key={`${w.kind}-${w.source}`} className="rv2-warning">
          <svg className="rv2-warning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth={2} strokeLinecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" /><path d="M12 11 V16" /><path d="M12 8 V8.5" />
          </svg>
          {w.message}
          {w.kind === "pending" && onCheckAgain && (
            <>
              {" "}
              <button type="button" className="results-summary-action" onClick={onCheckAgain}>
                Check again
              </button>
            </>
          )}
        </p>
      ))}
    </div>
  );
}
