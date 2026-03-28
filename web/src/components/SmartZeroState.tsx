import { memo } from "react";
import type { Diagnosis, DateSuggestion, ActionChip, SearchParams } from "../api";

type SearchMode = "find" | "exact";

interface SmartZeroStateProps {
  diagnosis?: Diagnosis;
  dateSuggestions?: DateSuggestion[];
  actionChips?: ActionChip[];
  searchDates?: { start: string; end: string };
  onSearch: (params: SearchParams, mode: SearchMode) => void;
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T12:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const e = new Date(end + "T12:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  return `${s} - ${e}`;
}

export const SmartZeroState = memo(function SmartZeroState({
  diagnosis,
  dateSuggestions,
  actionChips,
  searchDates,
  onSearch,
}: SmartZeroStateProps) {
  const hasDiagnosis = diagnosis != null;
  const hasSuggestions = dateSuggestions != null && dateSuggestions.length > 0;
  const hasActions = actionChips != null && actionChips.length > 0;

  const handleSuggestionClick = (suggestion: DateSuggestion) => {
    if (!searchDates) return;
    onSearch(
      {
        start_date: suggestion.start_date,
        end_date: suggestion.end_date,
      } as SearchParams,
      "find"
    );
  };

  const handleActionClick = (chip: ActionChip) => {
    const params = chip.params as Partial<SearchParams>;
    onSearch(params as SearchParams, "find");
  };

  return (
    <div className="smart-zero">
      <div className="smart-zero-section">
        <p className="smart-zero-explanation">
          {hasDiagnosis
            ? diagnosis.explanation
            : "No availability found for these dates."}
        </p>
        {!hasDiagnosis && (
          <p className="no-results-hint">
            Try different dates, a wider date range, or fewer nights.
            {searchDates &&
              " You can also watch specific campgrounds to get notified when sites open up."}
          </p>
        )}
      </div>

      {hasSuggestions && (
        <div className="smart-zero-section">
          <p className="smart-zero-suggestions">Try different dates</p>
          <div className="smart-zero-chips">
            {dateSuggestions.map((s, i) => (
              <button
                key={i}
                type="button"
                className="date-suggestion-chip"
                onClick={() => handleSuggestionClick(s)}
              >
                <span className="date-suggestion-range">
                  {formatDateRange(s.start_date, s.end_date)}
                </span>
                <span className="date-suggestion-count">
                  {s.campgrounds_with_availability}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {hasActions && (
        <div className="smart-zero-section">
          <div className="smart-zero-chips">
            {actionChips.map((chip, i) => (
              <button
                key={i}
                type="button"
                className={`action-chip${chip.action === "watch" ? " watch" : ""}`}
                onClick={() => handleActionClick(chip)}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
