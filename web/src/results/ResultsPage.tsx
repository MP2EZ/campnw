import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "./results.css";
import { lazy, Suspense, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import type { SearchParams } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { useSearchContext } from "../contexts/SearchContext";
import { AnswerHeader } from "./AnswerHeader";
import { DateChips } from "./DateChips";
import { DriveBands } from "./DriveBands";
import { FullGroup } from "./FullGroup";
import { fullGroupTitle } from "./candidates";
import { QuickPicks } from "./QuickPicks";
import { ZeroResults } from "./ZeroResults";
import { ResultsNotices } from "./ResultsNotices";
import { answerSentence, searchedAgo } from "./answer";
import { groupByDriveBand } from "./bands";
import { MapSheet } from "./MapSheet";
import { useMediaQuery } from "./media";
import { createSelectionStore, SelectionContext } from "./selection";

// Leaflet comes with this chunk: beside the list when it's wide enough, else
// in MapSheet once it's opened.
const ResultsMap = lazy(() => import("./ResultsMap"));
export const SPLIT_QUERY = "(min-width: 1024px)";

interface Props {
  maxResults: number;
  onCheckRest: (limit: number) => void;
  /** When the last search finished, for "searched 5 min ago". */
  completedAt: number | null;
  onSearch: (params: SearchParams, mode: SearchMode) => void;
  searchId?: string;
  /** The search ended in an error before it finished. */
  failed?: boolean;
}

// A clock that ticks every 30s, so the "searched … ago" label stays current.
const TICK = 30_000;
const subscribeClock = (cb: () => void) => {
  const id = setInterval(cb, TICK);
  return () => clearInterval(id);
};
const readClock = () => Math.floor(Date.now() / TICK) * TICK;

/**
 * Results v2 (v1.48): the answer, then the notices that qualify it, then
 * places. Mounted from App's one switch point when `useUiVersion()` is "v2".
 */
export default function ResultsPage({ maxResults, onCheckRest, completedAt, onSearch, searchId, failed }: Props) {
  const { results, loading, searchParams, filteredResults } = useSearchContext();
  const now = useSyncExternalStore(subscribeClock, readClock);
  const split = useMediaQuery(SPLIT_QUERY);
  const [selection] = useState(createSelectionStore);
  // Memoised: a new array would rebuild every pin (and drop the selection).
  const mapPlaces = useMemo(() => !results ? [] : [
    ...groupByDriveBand(filteredResults.filter((r) => r.total_available_sites > 0)).flatMap((b) => b.results),
    ...(results.unavailable ?? []),
  ], [results, filteredResults]);
  // A quick pick: open its band, then move to its card (n re-runs a repeat pick).
  const [pick, setPick] = useState<{ id: string; n: number } | null>(null);
  useEffect(() => {
    if (!pick) return;
    const name = document.getElementById(`rv2-card-${pick.id}`);
    name?.closest("article")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    name?.focus({ preventScroll: true });
  }, [pick]);
  if (!results) return null;

  const cards = filteredResults.filter((r) => r.total_available_sites > 0);
  const unavailable = results.unavailable ?? [];
  const zero = !loading && !failed && cards.length === 0;
  const sentence = answerSentence({
    params: searchParams,
    open: cards.length,
    checked: results.campgrounds_checked,
    notReleased: results.not_released_campgrounds ?? 0,
    loading,
    failed,
  });

  const page = (
    <section className="results results-v2" aria-labelledby="rv2-answer">
      <AnswerHeader
        sentence={sentence}
        searched={!loading && completedAt ? searchedAgo(completedAt, Math.max(now, completedAt)) : null}
        full={unavailable.length}
        fullTitle={fullGroupTitle(unavailable, searchParams)}
        coverage={{
          checked: results.campgrounds_checked,
          matched: results.campgrounds_matched,
          limit: maxResults,
          withAvailability: cards.length,
          nearby: !!searchParams?.from_location,
          loading,
          onCheckRest,
        }}
      />
      <DateChips params={searchParams} onSearch={onSearch} />
      <ResultsNotices results={results} withNotReleased={!zero} />
      {!loading && (
        <QuickPicks results={cards} params={searchParams}
          onPick={(id) => setPick((p) => ({ id, n: (p?.n ?? 0) + 1 }))} />
      )}
      <DriveBands results={cards} params={searchParams} reveal={pick?.id} />
      {zero ? (
        <ZeroResults results={results} places={unavailable} params={searchParams} onSearch={onSearch}
          searchId={searchId} />
      ) : (
        <FullGroup places={unavailable} params={searchParams} />
      )}
    </section>
  );
  // A pin opens its card's band, scrolls to it and moves focus there, like a quick pick.
  const onPin = (id: string) => {
    selection.select(id, "map");
    setPick((p) => ({ id, n: (p?.n ?? 0) + 1 }));
  };

  return (
    <SelectionContext.Provider value={selection}>
      <div className={split ? "rv2-split rv2-split--map" : "rv2-split"}>
        {page}
        {!split && <MapSheet places={mapPlaces} searchKey={searchParams} selection={selection} onSelect={onPin} />}
        {split && (
          <aside className="rv2-map-aside" aria-labelledby="rv2-map-h">
            <h2 id="rv2-map-h" className="sr-only">Map of results</h2>
            <p className="sr-only">The list has the same places.</p>
            <Suspense fallback={<div className="rv2-map-loading" />}>
              <ResultsMap places={mapPlaces} searchKey={searchParams} selection={selection} onSelect={onPin} />
            </Suspense>
          </aside>
        )}
      </div>
    </SelectionContext.Provider>
  );
}
