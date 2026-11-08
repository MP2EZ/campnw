import { useId, type ReactNode } from "react";
import {
  DRIVE_FROM, LONG_WEEKEND, WEEKEND, monthName, monthOptions,
  type BarState, type Equipment, type When,
} from "./searchState";
import { formatDateRange } from "../lib/dates";
import { addDays } from "./candidates";

/** The bar's popover contents. Each edits a draft; nothing searches until submit. */
export interface PanelProps {
  bar: BarState;
  onChange: (next: BarState) => void;
  today: string;
}

function Chip({ pressed, onClick, children, label }: {
  pressed: boolean; onClick: () => void; children: ReactNode; label?: string;
}) {
  return (
    <button type="button" className="sb-chip" aria-pressed={pressed} aria-label={label} onClick={onClick}>
      {children}
    </button>
  );
}

function Stepper({ label, value, min, max, unit, onChange }: {
  label: string; value: number; min: number; max: number;
  unit: [one: string, many: string]; onChange: (n: number) => void;
}) {
  const id = useId();
  return (
    <div className="sb-field sb-stepper" role="group" aria-labelledby={id}>
      <span id={id} className="sb-field-label">{label}</span>
      <div className="sb-stepper-row">
        <button type="button" className="sb-step" aria-label={`Fewer ${unit[1]}`}
          disabled={value <= min} onClick={() => onChange(value - 1)}>−</button>
        <output className="sb-step-value" aria-live="polite">
          {value} {value === 1 ? unit[0] : unit[1]}
        </output>
        <button type="button" className="sb-step" aria-label={`More ${unit[1]}`}
          disabled={value >= max} onClick={() => onChange(value + 1)}>+</button>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <div className="sb-field">
      <span id={id} className="sb-field-label">{label}</span>
      <div className="sb-chips" role="group" aria-labelledby={id}>{children}</div>
    </div>
  );
}

// ─── Where ───────────────────────────────────────────────────────────

export function FromSelect({ bar, onChange }: PanelProps) {
  const id = useId();
  return (
    <label className="sb-field" htmlFor={id}>
      <span className="sb-field-label">Drive from</span>
      <select id={id} className="sb-select" value={bar.from}
        onChange={(e) => onChange({ ...bar, from: e.target.value })}>
        {DRIVE_FROM.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        {bar.from && !DRIVE_FROM.some(([k]) => k === bar.from) && <option value={bar.from}>{bar.from}</option>}
      </select>
    </label>
  );
}

// ─── When ────────────────────────────────────────────────────────────

const sameWhen = (a: When, b: When) => JSON.stringify(a) === JSON.stringify(b);

export function WhenPanel({ bar, onChange, today }: PanelProps) {
  const exact = bar.when.kind === "exact";
  const setWhen = (when: When) => onChange({ ...bar, when });
  const startExact = () => {
    const start = addDays(today, 14);
    setWhen({ kind: "exact", start, end: addDays(start, bar.nights) });
  };
  const ex = bar.when.kind === "exact" ? bar.when : null;

  return (
    <>
      <Group label="Dates">
        <Chip pressed={bar.when.kind === "this-weekend"} onClick={() => setWhen({ kind: "this-weekend" })}>This weekend</Chip>
        <Chip pressed={bar.when.kind === "next-weekend"} onClick={() => setWhen({ kind: "next-weekend" })}>Next weekend</Chip>
        {monthOptions(today, bar.when.kind === "month" ? bar.when.month : undefined).map((month) => (
          <Chip key={month} pressed={sameWhen(bar.when, { kind: "month", month })}
            label={`${monthName(month)} ${month.slice(0, 4)}`}
            onClick={() => setWhen({ kind: "month", month })}>
            {monthName(month, "short")}
          </Chip>
        ))}
        {bar.when.kind === "range" && (
          <Chip pressed onClick={() => {}}>{formatDateRange(bar.when.start, bar.when.end)}</Chip>
        )}
        <Chip pressed={exact} onClick={exact ? () => {} : startExact}>Exact dates</Chip>
      </Group>

      {ex ? (
        <div className="sb-dates">
          <label className="sb-field">
            <span className="sb-field-label">Arrive</span>
            <input type="date" className="sb-input" value={ex.start} min={today}
              onChange={(e) => {
                const start = e.target.value;
                if (!start) return;
                setWhen({ kind: "exact", start, end: ex.end > start ? ex.end : addDays(start, 1) });
              }} />
          </label>
          <label className="sb-field">
            <span className="sb-field-label">Leave</span>
            <input type="date" className="sb-input" value={ex.end} min={addDays(ex.start, 1)}
              onChange={(e) => e.target.value > ex.start && setWhen({ ...ex, end: e.target.value })} />
          </label>
        </div>
      ) : (
        <>
          <Group label="Which days">
            <Chip pressed={bar.days === WEEKEND} onClick={() => onChange({ ...bar, days: WEEKEND })}>Weekends</Chip>
            <Chip pressed={bar.days === LONG_WEEKEND} onClick={() => onChange({ ...bar, days: LONG_WEEKEND })}>Long weekends</Chip>
            <Chip pressed={bar.days === ""} onClick={() => onChange({ ...bar, days: "" })}>Any days</Chip>
          </Group>
          <Stepper label="Nights" value={bar.nights} min={1} max={14} unit={["night", "nights"]}
            onChange={(nights) => onChange({ ...bar, nights })} />
        </>
      )}
    </>
  );
}

// ─── Who ─────────────────────────────────────────────────────────────

const RIGS: Array<[Equipment, string]> = [["tent", "Tent"], ["van", "Van"], ["trailer", "Trailer or RV"]];
const LENGTHS = [20, 25, 30, 35, 40];

export function WhoPanel({ bar, onChange }: PanelProps) {
  const lengthId = useId();
  return (
    <>
      <Stepper label="People" value={bar.people} min={1} max={20} unit={["person", "people"]}
        onChange={(people) => onChange({ ...bar, people })} />
      <Group label="Sleeping in">
        {RIGS.map(([key, label]) => (
          <Chip key={key} pressed={bar.equipment === key}
            onClick={() => onChange({ ...bar, equipment: bar.equipment === key ? null : key, rigLength: key === "trailer" ? bar.rigLength : null })}>
            {label}
          </Chip>
        ))}
      </Group>
      {bar.equipment === "trailer" && (
        <label className="sb-field" htmlFor={lengthId}>
          <span className="sb-field-label">Length</span>
          <select id={lengthId} className="sb-select" value={bar.rigLength ?? ""}
            onChange={(e) => onChange({ ...bar, rigLength: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Not sure</option>
            {LENGTHS.map((ft) => <option key={ft} value={ft}>{ft === 40 ? "40′ or more" : `Up to ${ft}′`}</option>)}
          </select>
        </label>
      )}
    </>
  );
}

// ─── Drive ───────────────────────────────────────────────────────────

const DRIVES: Array<[number | null, string]> = [[60, "1 h"], [120, "2 h"], [180, "3 h"], [240, "4 h"], [300, "5 h"], [null, "Any"]];

export function DrivePanel({ bar, onChange }: PanelProps) {
  return (
    <>
      <Group label="Longest drive">
        {DRIVES.map(([minutes, label]) => (
          <Chip key={label} pressed={bar.maxDrive === minutes}
            label={minutes ? `Up to ${label.replace(" h", minutes === 60 ? " hour" : " hours")}` : "Any distance"}
            onClick={() => onChange({ ...bar, maxDrive: minutes })}>
            {label}
          </Chip>
        ))}
      </Group>
      {bar.name && <p className="sb-note">Searching for {bar.name} ignores drive time.</p>}
    </>
  );
}
