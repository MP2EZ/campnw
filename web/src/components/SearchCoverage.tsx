import type { ReactNode } from "react";

/** The API's ceiling on how many campgrounds one search may check (`limit`). */
export const MAX_SEARCH_LIMIT = 50;

interface Props {
  checked: number;
  /** Undefined until the stream reports it; reads as "not capped". */
  matched?: number;
  /** How many the running search will check, once the stream has said. */
  planned?: number;
  /** The `limit` the search ran with. */
  limit: number;
  withAvailability: number;
  /** True when results are ordered by drive time from an origin. */
  nearby: boolean;
  /** True when a drive limit bounds the pool, so it can be called "nearby". */
  driveLimit?: boolean;
  loading: boolean;
  onCheckRest: (limit: number) => void;
  /** Appended to the line (results v2: when the search ran). */
  after?: ReactNode;
}

const n = (x: number) => x.toLocaleString("en-US");

/**
 * Results summary line. A search checks only the closest `limit` matches from
 * each booking system, so when more matched than were checked it says so —
 * "Checked the 20 closest of 46" — rather than letting a capped search read as
 * a complete one.
 */
export function SearchCoverage({
  checked, matched, planned, limit, withAvailability, nearby, driveLimit = false, loading, onCheckRest, after,
}: Props) {
  const capped = matched !== undefined && matched > checked;
  const availability = `${withAvailability} with availability`;

  if (!capped) {
    // While running, a bare count reads as unbounded (it can sit still for 20s
    // on a slow provider), so give it the total it's heading for.
    const count = !loading ? `${n(checked)} campground${checked === 1 ? "" : "s"}`
      : planned ? `${n(checked)} of ${n(planned)} campgrounds` : `${n(checked)} campgrounds so far`;
    return (
      <p className="results-summary">
        Checked {count} — {availability}{after}
      </p>
    );
  }

  // matched <= MAX means one more search can check everything; beyond it the
  // API cap makes "the rest" unreachable.
  const canCheckRest = !loading && limit < MAX_SEARCH_LIMIT && matched <= MAX_SEARCH_LIMIT;
  // "Nearby" only when a drive limit bounds the pool; 1,368 aren't nearby.
  const pool = `${n(matched)} ${!nearby ? "matching " : driveLimit ? "nearby " : ""}campgrounds`;
  // More checked than the limit means the cap applied per booking system.
  const which = checked > limit
    ? `${n(checked)} of ${pool}, ${nearby ? `the ${n(limit)} closest` : `up to ${n(limit)}`} from each booking system`
    : nearby ? `the ${n(checked)} closest of ${pool}` : `${n(checked)} of ${pool}`;

  return (
    <p className="results-summary">
      Checked {which}
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
      ) : null}
      {after}
    </p>
  );
}
