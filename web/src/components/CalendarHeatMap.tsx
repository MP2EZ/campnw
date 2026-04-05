import { memo, useMemo } from "react";
import type { SearchResponse } from "../api";

interface Props {
  results: SearchResponse;
  startDate: string;
  endDate: string;
  /** Active day-of-week filter — preset name or comma-separated day numbers (0=Sun). */
  daysOfWeek?: string;
}

const DOW_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const DOW_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** Resolve a day filter string into a Set of JS day-of-week indices (0=Sun).
 *  The API uses Python convention (0=Mon), so we convert: (apiDay + 1) % 7. */
function resolveActiveDays(daysOfWeek?: string): Set<number> | null {
  if (!daysOfWeek) return null;
  // Comma-separated day numbers in API convention (0=Mon, 6=Sun)
  const apiNums = daysOfWeek.split(",").map(Number).filter((n) => n >= 0 && n <= 6);
  if (apiNums.length === 0 || apiNums.length === 7) return null;
  // Convert to JS convention (0=Sun)
  return new Set(apiNums.map((d) => (d + 1) % 7));
}

/** Format active days as a readable label for the context tag. */
function formatDayLabel(activeDays: Set<number>): string {
  const sorted = [...activeDays].sort((a, b) => a - b);
  const names = sorted.map((d) => DOW_FULL[d].slice(0, 3));
  if (names.length <= 3) return names.join(", ");
  return `${names[0]}–${names[names.length - 1]}`;
}

function computeDensity(
  results: SearchResponse,
  startDate: string,
  endDate: string
): Map<string, number> {
  const density = new Map<string, number>();
  const start = new Date(startDate + "T12:00:00");
  const end = new Date(endDate + "T12:00:00");

  const d = new Date(start);
  while (d <= end) {
    density.set(d.toISOString().split("T")[0], 0);
    d.setDate(d.getDate() + 1);
  }

  for (const result of results.results) {
    for (const w of result.windows) {
      if (w.is_fcfs) continue;
      const wStart = new Date(w.start_date + "T12:00:00");
      const wEnd = new Date(w.end_date + "T12:00:00");
      const cursor = new Date(wStart);
      while (cursor <= wEnd) {
        const key = cursor.toISOString().split("T")[0];
        if (density.has(key)) {
          density.set(key, (density.get(key) || 0) + 1);
        }
        cursor.setDate(cursor.getDate() + 1);
      }
    }
  }

  return density;
}

interface WeekColumn {
  weekIdx: number;
  monthLabel?: string; // shown above the first week of each month
  days: {
    date: string;
    dow: number;
    count: number;
    label: string;
  }[];
}

function buildWeeks(
  startDate: string,
  endDate: string,
  density: Map<string, number>
): WeekColumn[] {
  const weeks: WeekColumn[] = [];
  const start = new Date(startDate + "T12:00:00");
  const end = new Date(endDate + "T12:00:00");

  // Align to the Sunday of the start week
  const cursor = new Date(start);
  cursor.setDate(cursor.getDate() - cursor.getDay());

  let weekIdx = 0;
  let lastMonth = -1;

  while (cursor <= end || cursor.getDay() !== 0) {
    const week: WeekColumn = { weekIdx, days: [] };

    for (let dow = 0; dow < 7; dow++) {
      const key = cursor.toISOString().split("T")[0];
      const inRange = cursor >= start && cursor <= end;

      if (inRange) {
        // Check if we need a month label
        if (cursor.getMonth() !== lastMonth) {
          week.monthLabel = cursor.toLocaleDateString("en-US", {
            month: "short",
          });
          lastMonth = cursor.getMonth();
        }

        week.days.push({
          date: key,
          dow,
          count: density.get(key) || 0,
          label: cursor.toLocaleDateString("en-US", {
            weekday: "short",
            month: "short",
            day: "numeric",
          }),
        });
      }
      cursor.setDate(cursor.getDate() + 1);
    }

    if (week.days.length > 0) {
      weeks.push(week);
      weekIdx++;
    }

    if (cursor > end && cursor.getDay() === 0) break;
  }

  return weeks;
}

function densityLevel(count: number, max: number): number {
  if (count === 0) return 0;
  const ratio = count / Math.max(max, 1);
  if (ratio < 0.25) return 1;
  if (ratio < 0.5) return 2;
  if (ratio < 0.75) return 3;
  return 4;
}

export const CalendarHeatMap = memo(function CalendarHeatMap({ results, startDate, endDate, daysOfWeek }: Props) {
  const density = useMemo(
    () => computeDensity(results, startDate, endDate),
    [results, startDate, endDate]
  );

  const weeks = useMemo(
    () => buildWeeks(startDate, endDate, density),
    [startDate, endDate, density]
  );

  const maxCount = useMemo(() => {
    let max = 0;
    for (const v of density.values()) if (v > max) max = v;
    return max;
  }, [density]);

  const activeDays = useMemo(() => resolveActiveDays(daysOfWeek), [daysOfWeek]);

  if (results.results.length === 0 || weeks.length === 0) return null;

  // Build a lookup: weekIdx -> dow -> day data
  const grid: Map<string, { count: number; label: string; date: string }> =
    new Map();
  for (const week of weeks) {
    for (const day of week.days) {
      grid.set(`${week.weekIdx}-${day.dow}`, day);
    }
  }

  const ariaLabel = activeDays
    ? `Availability density, showing ${formatDayLabel(activeDays)}`
    : "Availability density";

  return (
    <div className="heatmap" role="group" aria-label={ariaLabel}>
      <div className="heatmap-header-row">
        <span className="heatmap-title">Site Availability</span>
        <div className="heatmap-header-right">
          {activeDays && (
            <span className="heatmap-day-filter-tag">
              Showing: {formatDayLabel(activeDays)}
            </span>
          )}
          <div className="heatmap-legend">
            <span className="heatmap-legend-label">0 sites</span>
            {[0, 1, 2, 3, 4].map((level) => (
              <span key={level} className={`heatmap-swatch density-${level}`} />
            ))}
            <span className="heatmap-legend-label">{maxCount}+ sites</span>
          </div>
        </div>
      </div>

      <div className="heatmap-scroll">
        <div
          className="heatmap-grid"
          style={
            {
              "--week-count": weeks.length,
            } as React.CSSProperties
          }
        >
          {/* Month labels row */}
          <span className="heatmap-corner" />
          {weeks.map((w) => (
            <span key={`ml-${w.weekIdx}`} className="heatmap-month-label">
              {w.monthLabel || ""}
            </span>
          ))}

          {/* Day rows */}
          {DOW_LABELS.map((label, dow) => {
            const isDimmed = activeDays !== null && !activeDays.has(dow);
            const isWeekend = dow === 0 || dow === 5 || dow === 6;
            return (
              <div key={`row-${dow}`} className="heatmap-row" style={{ display: "contents" }}>
                <span
                  className={`heatmap-dow${isWeekend ? " weekend" : ""}${isDimmed ? " dimmed" : ""}`}
                  aria-label={DOW_FULL[dow]}
                >
                  {label}
                </span>
                {weeks.map((w) => {
                  const day = grid.get(`${w.weekIdx}-${dow}`);
                  if (!day) {
                    return (
                      <span
                        key={`e-${w.weekIdx}-${dow}`}
                        className={`heatmap-cell empty${isDimmed ? " dimmed" : ""}`}
                      />
                    );
                  }
                  const level = densityLevel(day.count, maxCount);
                  return (
                    <span
                      key={`c-${w.weekIdx}-${dow}`}
                      className={`heatmap-cell density-${level}${isWeekend ? " weekend-cell" : ""}${isDimmed ? " dimmed" : ""}`}
                      aria-label={`${day.label}: ${day.count} sites available`}
                      title={`${day.label}: ${day.count} sites`}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
});
