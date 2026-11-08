import { track, type SearchParams } from "../api";
import type { SearchMode } from "../hooks/useSearch";
import { barToParams, EDIT_DATES_EVENT, localToday, paramsToBar, quickDates } from "./searchState";

interface Props {
  params: SearchParams | null;
  onSearch: (params: SearchParams, mode: SearchMode) => void;
}

/**
 * One-tap date changes under the answer (P4a, phones only): this weekend,
 * next weekend, a month, or "Pick dates" to open the search bar's sheet.
 * Everything else about the search stays as it was.
 */
export function DateChips({ params, onSearch }: Props) {
  if (!params?.start_date) return null;
  const today = localToday();
  const bar = paramsToBar(params, today);
  return (
    <div className="rv2-dates" role="group" aria-label="Dates">
      {quickDates(bar, today).map((chip) => (
        <button key={chip.label} type="button" className="rv2-date" aria-pressed={chip.pressed}
          onClick={() => {
            if (chip.pressed) return;
            track("results_date_chip", { when: chip.when.kind });
            onSearch(barToParams({ ...bar, when: chip.when }, today, params), "find");
          }}>
          {chip.label}
          {chip.year && <span className="sr-only">, {chip.year}</span>}
        </button>
      ))}
      <button type="button" className="rv2-date rv2-date--pick" aria-haspopup="dialog"
        onClick={() => window.dispatchEvent(new Event(EDIT_DATES_EVENT))}>
        Pick dates
      </button>
    </div>
  );
}
