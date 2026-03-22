import { useMemo } from "react";
import type { SearchResponse } from "./api";

interface Props {
  results: SearchResponse;
  startDate: string;
  endDate: string;
  onDateClick?: (date: string) => void;
  selectedDate?: string | null;
}

interface DayCell {
  date: string;
  dayOfMonth: number;
  dayOfWeek: number; // 0=Sun
  siteCount: number;
  label: string; // e.g. "Mon Jun 1"
}

function computeDensity(
  results: SearchResponse,
  startDate: string,
  endDate: string
): Map<string, number> {
  const density = new Map<string, number>();
  const start = new Date(startDate + "T12:00:00");
  const end = new Date(endDate + "T12:00:00");

  // Initialize all dates to 0
  const d = new Date(start);
  while (d <= end) {
    density.set(d.toISOString().split("T")[0], 0);
    d.setDate(d.getDate() + 1);
  }

  // Count available sites per day from windows
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

function getMonths(startDate: string, endDate: string): string[] {
  const months: string[] = [];
  const start = new Date(startDate + "T12:00:00");
  const end = new Date(endDate + "T12:00:00");
  const d = new Date(start.getFullYear(), start.getMonth(), 1);
  while (d <= end) {
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    d.setMonth(d.getMonth() + 1);
  }
  return months;
}

function getDaysForMonth(
  yearMonth: string,
  density: Map<string, number>,
  startDate: string,
  endDate: string
): DayCell[] {
  const [year, month] = yearMonth.split("-").map(Number);
  const days: DayCell[] = [];
  const d = new Date(year, month - 1, 1, 12);

  while (d.getMonth() === month - 1) {
    const key = d.toISOString().split("T")[0];
    if (key >= startDate && key <= endDate) {
      days.push({
        date: key,
        dayOfMonth: d.getDate(),
        dayOfWeek: d.getDay(),
        siteCount: density.get(key) || 0,
        label: d.toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
        }),
      });
    }
    d.setDate(d.getDate() + 1);
  }
  return days;
}

function cellColor(count: number, max: number): string {
  if (count === 0) return "var(--heatmap-0)";
  const ratio = Math.min(count / Math.max(max, 1), 1);
  if (ratio < 0.25) return "var(--heatmap-1)";
  if (ratio < 0.5) return "var(--heatmap-2)";
  if (ratio < 0.75) return "var(--heatmap-3)";
  return "var(--heatmap-4)";
}

export function CalendarHeatMap({
  results,
  startDate,
  endDate,
  onDateClick,
  selectedDate,
}: Props) {
  const density = useMemo(
    () => computeDensity(results, startDate, endDate),
    [results, startDate, endDate]
  );

  const months = useMemo(
    () => getMonths(startDate, endDate),
    [startDate, endDate]
  );

  const maxCount = useMemo(() => {
    let max = 0;
    for (const v of density.values()) {
      if (v > max) max = v;
    }
    return max;
  }, [density]);

  if (results.results.length === 0) return null;

  const dayHeaders = ["S", "M", "T", "W", "T", "F", "S"];

  return (
    <div className="heatmap" role="group" aria-label="Availability calendar">
      <div className="heatmap-legend">
        <span className="heatmap-legend-label">Fewer sites</span>
        <span className="heatmap-swatch" style={{ background: "var(--heatmap-0)" }} />
        <span className="heatmap-swatch" style={{ background: "var(--heatmap-1)" }} />
        <span className="heatmap-swatch" style={{ background: "var(--heatmap-2)" }} />
        <span className="heatmap-swatch" style={{ background: "var(--heatmap-3)" }} />
        <span className="heatmap-swatch" style={{ background: "var(--heatmap-4)" }} />
        <span className="heatmap-legend-label">More sites</span>
      </div>

      {months.map((ym) => {
        const [year, month] = ym.split("-").map(Number);
        const monthName = new Date(year, month - 1).toLocaleDateString(
          "en-US",
          { month: "long", year: "numeric" }
        );
        const days = getDaysForMonth(ym, density, startDate, endDate);
        if (days.length === 0) return null;

        // Pad start for day-of-week alignment
        const firstDow = days[0].dayOfWeek;

        return (
          <div key={ym} className="heatmap-month">
            <h4 className="heatmap-month-title">{monthName}</h4>
            <div className="heatmap-grid" role="grid" aria-label={monthName}>
              {dayHeaders.map((d, i) => (
                <span key={i} className="heatmap-header" role="columnheader">
                  {d}
                </span>
              ))}
              {Array.from({ length: firstDow }).map((_, i) => (
                <span key={`pad-${i}`} className="heatmap-cell empty" />
              ))}
              {days.map((day) => (
                  <button
                    key={day.date}
                    className={`heatmap-cell ${selectedDate === day.date ? "selected" : ""}`}
                    style={{ background: cellColor(day.siteCount, maxCount) }}
                    role="gridcell"
                    aria-label={`${day.label}: ${day.siteCount} sites available`}
                    onClick={() => onDateClick?.(day.date)}
                    type="button"
                  >
                    <span className="heatmap-day">{day.dayOfMonth}</span>
                    {day.siteCount > 0 && (
                      <span className="heatmap-count">{day.siteCount}</span>
                    )}
                  </button>
                ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
