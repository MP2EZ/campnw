import type { ReactNode } from "react";

/** The API's ceiling on how many campgrounds one search may check (`limit`). */
export const MAX_SEARCH_LIMIT = 50;

interface Props {
  checked: number;
  /** Undefined until the stream reports it; reads as "not capped". */
  matched?: number;
  /** The `limit` the search ran with. */
  limit: number;
  withAvailability: number;
  /** True when results are ordered by drive time from an origin. */
  nearby: boolean;
  loading: boolean;
  onCheckRest: (limit: number) => void;
  /** Appended to the line (results v2: when the search ran). */
  after?: ReactNode;
}

/**
 * Results summary line. A search checks only the closest `limit` matches, so
 * when more matched than were checked it says so — "Checked 20 of 46" — rather
 * than letting a capped search read as a complete one.
 */
export function SearchCoverage({
  checked, matched, limit, withAvailability, nearby, loading, onCheckRest, after,
}: Props) {
  const capped = matched !== undefined && matched > checked;
  const availability = `${withAvailability} with availability`;

  if (!capped) {
    return (
      <p className="results-summary">
        Checked {checked} campgrounds — {availability}{after}
      </p>
    );
  }

  // matched <= MAX means one more search can check everything; beyond it the
  // API cap makes "the rest" unreachable, so say what is being shown instead.
  const canCheckRest = !loading && limit < MAX_SEARCH_LIMIT && matched <= MAX_SEARCH_LIMIT;

  return (
    <p className="results-summary">
      Checked {checked} of {matched} {nearby ? "nearby" : "matching"} campgrounds
      {" — "}{availability}
      {canCheckRest ? (
        <>
          {" · "}
          <button
            type="button"
            className="results-summary-action"
            onClick={() => onCheckRest(matched)}
          >
            Check the rest
          </button>
        </>
      ) : (
        !loading && ` · Showing the ${limit} closest`
      )}
      {after}
    </p>
  );
}
