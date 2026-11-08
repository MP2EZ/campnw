import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "./results.css";
import { useSyncExternalStore } from "react";
import type { SearchParams } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { useSearchContext } from "../contexts/SearchContext";
import { SmartZeroState } from "../components/SmartZeroState";
import { AnswerHeader } from "./AnswerHeader";
import { DriveBands } from "./DriveBands";
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
  const { results, loading, searchParams, searchDates, filteredResults } = useSearchContext();
  const now = useSyncExternalStore(subscribeClock, readClock);
  if (!results) return null;

  const cards = filteredResults.filter((r) => r.total_available_sites > 0);
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
      <ResultsNotices results={results} />
      <DriveBands results={cards} params={searchParams} />
      {!loading && !failed && cards.length === 0 && (
        <SmartZeroState
          diagnosis={results.diagnosis}
          dateSuggestions={results.date_suggestions}
          actionChips={results.action_chips}
          searchDates={searchDates || undefined}
          searchId={searchId}
          notReleased={results.not_released_campgrounds}
          onSearch={onSearch}
        />
      )}
    </section>
  );
}
