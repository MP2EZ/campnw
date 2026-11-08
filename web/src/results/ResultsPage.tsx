import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "./results.css";
import { useEffect, useState, useSyncExternalStore } from "react";
import type { SearchParams } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { useSearchContext } from "../contexts/SearchContext";
import { AnswerHeader } from "./AnswerHeader";
import { DriveBands } from "./DriveBands";
import { FullGroup } from "./FullGroup";
import { QuickPicks } from "./QuickPicks";
import { ZeroResults } from "./ZeroResults";
import { ResultsNotices } from "./ResultsNotices";
import { answerSentence, searchedAgo } from "./answer";

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

  return (
    <section className="results results-v2" aria-labelledby="rv2-answer">
      <AnswerHeader
        sentence={sentence}
        searched={!loading && completedAt ? searchedAgo(completedAt, Math.max(now, completedAt)) : null}
        full={unavailable.length}
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
}
