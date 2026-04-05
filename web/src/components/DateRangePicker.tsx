import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { track } from "../api";

interface Props {
  startDate: string;
  endDate: string;
  onChange: (start: string, end: string) => void;
  mode: "find" | "exact";
}

interface MonthGridProps {
  year: number;
  month: number;
  showNav: boolean;
  prevMonth: () => void;
  nextMonth: () => void;
  renderStart: Date | null;
  renderEnd: Date | null;
  hoverDate: Date | null;
  selecting: "start" | "done";
  tempStart: Date | null;
  today: Date;
  handleDayClick: (d: Date) => void;
  setHoverDate: (d: Date) => void;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const DOW_HEADERS = ["S", "M", "T", "W", "T", "F", "S"];

function toDateKey(d: Date): string {
  return d.toISOString().split("T")[0];
}

function parseDate(s: string): Date {
  return new Date(s + "T12:00:00");
}

function formatRange(start: string, end: string): string {
  const s = parseDate(start);
  const e = parseDate(end);
  const sm = SHORT_MONTHS[s.getMonth()];
  const em = SHORT_MONTHS[e.getMonth()];
  if (s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear()) {
    return `${sm} ${s.getDate()} – ${e.getDate()}`;
  }
  return `${sm} ${s.getDate()} – ${em} ${e.getDate()}`;
}

function getMonthDays(year: number, month: number): (Date | null)[] {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  return cells;
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

function isBetween(d: Date, start: Date, end: Date): boolean {
  return d > start && d < end;
}

const MonthGrid = memo(function MonthGrid({
  year, month, showNav, prevMonth, nextMonth,
  renderStart, renderEnd, hoverDate, selecting, tempStart, today,
  handleDayClick, setHoverDate,
}: MonthGridProps) {
  const days = useMemo(() => getMonthDays(year, month), [year, month]);

  const ariaLabels = useMemo(() => {
    const labels: string[] = [];
    for (const day of days) {
      if (day) {
        labels.push(day.toLocaleDateString("en-US", {
          weekday: "long", month: "long", day: "numeric", year: "numeric",
        }));
      } else {
        labels.push("");
      }
    }
    return labels;
  }, [days]);

  return (
    <div className="drp-month">
      <div className="drp-month-header">
        {showNav ? (
          <button type="button" className="drp-nav" onClick={prevMonth} aria-label="Previous month">◀</button>
        ) : <span />}
        <span className="drp-month-title">{MONTH_NAMES[month]} {year}</span>
        {!showNav ? (
          <button type="button" className="drp-nav" onClick={nextMonth} aria-label="Next month">▶</button>
        ) : <span />}
      </div>
      <div className="drp-grid">
        {DOW_HEADERS.map((d, i) => (
          <span key={`dow-${i}`} className="drp-dow">{d}</span>
        ))}
        {days.map((day, i) => {
          if (!day) return <span key={`empty-${i}`} className="drp-day drp-empty" />;

          const isPast = day < today;
          const isStart = renderStart && isSameDay(day, renderStart);
          const isEnd = renderEnd && isSameDay(day, renderEnd);
          const inRange = renderStart && renderEnd && isBetween(day, renderStart, renderEnd);
          const isToday = isSameDay(day, today);
          const isPreview = selecting === "start" && hoverDate && tempStart
            && isBetween(day,
              hoverDate < tempStart ? hoverDate : tempStart,
              hoverDate < tempStart ? tempStart : hoverDate,
            );

          let cls = "drp-day";
          if (isPast) cls += " past";
          if (isToday) cls += " today";
          if (isStart && isEnd) cls += " single";
          else if (isStart) cls += " start";
          else if (isEnd) cls += " end";
          else if (inRange) cls += " in-range";
          else if (isPreview) cls += " preview";

          return (
            <button
              key={`day-${i}`}
              type="button"
              className={cls}
              disabled={isPast}
              onClick={() => handleDayClick(day)}
              onMouseEnter={() => selecting === "start" && setHoverDate(day)}
              aria-label={ariaLabels[i]}
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
});

export const DateRangePicker = memo(function DateRangePicker({
  startDate, endDate, onChange, mode,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [selecting, setSelecting] = useState<"start" | "done">("done");
  const [tempStart, setTempStart] = useState<Date | null>(null);
  const [hoverDate, setHoverDate] = useState<Date | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Calendar view starts at the month of the start date
  const initialMonth = useMemo(() => {
    const d = parseDate(startDate);
    return { year: d.getFullYear(), month: d.getMonth() };
  }, [startDate]);

  const [viewYear, setViewYear] = useState(initialMonth.year);
  const [viewMonth, setViewMonth] = useState(initialMonth.month);

  // Sync view when startDate prop changes externally (presets)
  useEffect(() => {
    const d = parseDate(startDate);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  }, [startDate]);

  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  const start = useMemo(() => parseDate(startDate), [startDate]);
  const end = useMemo(() => parseDate(endDate), [endDate]);

  // Navigate months
  const prevMonth = useCallback(() => {
    setViewMonth((m) => {
      if (m === 0) { setViewYear((y) => y - 1); return 11; }
      return m - 1;
    });
  }, []);

  const nextMonth = useCallback(() => {
    setViewMonth((m) => {
      if (m === 11) { setViewYear((y) => y + 1); return 0; }
      return m + 1;
    });
  }, []);

  // Second month
  const month2Year = viewMonth === 11 ? viewYear + 1 : viewYear;
  const month2Month = (viewMonth + 1) % 12;

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSelecting("done");
        setTempStart(null);
        setHoverDate(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  // Escape to close
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setIsOpen(false);
        setSelecting("done");
        setTempStart(null);
        setHoverDate(null);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen]);

  const handleDayClick = useCallback((d: Date) => {
    if (d < today) return;

    if (selecting === "done" || !tempStart) {
      // First click: set start
      setTempStart(d);
      setSelecting("start");
    } else {
      // Second click: set end
      let s = tempStart;
      let e = d;
      if (e < s) { [s, e] = [e, s]; }
      const startKey = toDateKey(s);
      const endKey = toDateKey(e);
      const rangeDays = Math.round((e.getTime() - s.getTime()) / 86400000);
      onChange(startKey, endKey);
      track("date_range_selected", { start: startKey, end: endKey, range_days: rangeDays });
      setSelecting("done");
      setTempStart(null);
      setHoverDate(null);
      setIsOpen(false);
    }
  }, [selecting, tempStart, onChange, today]);

  const handleDone = useCallback(() => {
    setIsOpen(false);
    setSelecting("done");
    setTempStart(null);
    setHoverDate(null);
  }, []);

  const handleClear = useCallback(() => {
    setTempStart(null);
    setSelecting("done");
    setHoverDate(null);
  }, []);

  // Compute visual range for rendering
  const rangeStart = tempStart || start;
  const rangeEnd = selecting === "start" && hoverDate
    ? (hoverDate < rangeStart ? hoverDate : hoverDate)
    : (selecting === "start" ? null : end);

  // Ensure correct order for rendering
  const renderStart = rangeEnd && rangeEnd < rangeStart ? rangeEnd : rangeStart;
  const renderEnd = rangeEnd && rangeEnd < rangeStart ? rangeStart : rangeEnd;

  const handleHoverDate = useCallback((d: Date) => setHoverDate(d), []);

  const label = mode === "find" ? "Search between" : "Check in – out";

  return (
    <div className="drp-wrap" ref={ref}>
      <div
        className={`drp-trigger${isOpen ? " open" : ""}`}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setIsOpen(!isOpen); } }}
        tabIndex={0}
        role="button"
        aria-expanded={isOpen}
        aria-label={`${label}: ${formatRange(startDate, endDate)}`}
      >
        <svg className="drp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
        <div className="drp-text">
          <span className="drp-label">{label}</span>
          <span className="drp-value">{formatRange(startDate, endDate)}</span>
        </div>
        <span className="drp-arrow" aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
      </div>

      {isOpen && (
        <div className="drp-popover">
          <div className="drp-months">
            <MonthGrid
              year={viewYear} month={viewMonth} showNav={true}
              prevMonth={prevMonth} nextMonth={nextMonth}
              renderStart={renderStart} renderEnd={renderEnd}
              hoverDate={hoverDate} selecting={selecting}
              tempStart={tempStart} today={today}
              handleDayClick={handleDayClick} setHoverDate={handleHoverDate}
            />
            <MonthGrid
              year={month2Year} month={month2Month} showNav={false}
              prevMonth={prevMonth} nextMonth={nextMonth}
              renderStart={renderStart} renderEnd={renderEnd}
              hoverDate={hoverDate} selecting={selecting}
              tempStart={tempStart} today={today}
              handleDayClick={handleDayClick} setHoverDate={handleHoverDate}
            />
          </div>
          {selecting === "start" && (
            <div className="drp-hint">Click an end date</div>
          )}
          <div className="drp-footer">
            <button type="button" className="drp-footer-btn" onClick={handleClear}>Clear</button>
            <button type="button" className="drp-footer-btn primary" onClick={handleDone}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
});
