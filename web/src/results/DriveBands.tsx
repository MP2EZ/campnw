import { useState } from "react";
import type { CampgroundResult, SearchParams } from "../api";
import { groupByDriveBand, type DriveBand } from "./bands";
import { CampgroundCard } from "./CampgroundCard";

const BAND_LIMIT = 5;

const places = (n: number) => `${n} place${n === 1 ? "" : "s"}`;

function moreLabel(band: DriveBand, n: number): string {
  if (band.key === "h0") return `Show ${n} more under 1 hour`;
  if (band.key.startsWith("h")) return `Show ${n} more within ${band.title}`;
  if (band.key === "boat-in") return `Show ${n} more boat-in ${n === 1 ? "place" : "places"}`;
  return `Show ${n} more`;
}

function Band({ band, params, firstRank }: { band: DriveBand; params: SearchParams | null; firstRank: number }) {
  const [all, setAll] = useState(false);
  // Hiding one card behind a button saves nothing.
  const cut = band.results.length > BAND_LIMIT + 1 ? BAND_LIMIT : band.results.length;
  const hidden = band.results.length - cut;
  const shown = all ? band.results : band.results.slice(0, cut);
  const id = `rv2-band-${band.key}`;

  const body = (
    <>
      {band.note && <p className="rv2-band-note">{band.note}</p>}
      <div className="rv2-list">
        {shown.map((r, i) => (
          <CampgroundCard key={r.facility_id} result={r} params={params} rank={firstRank + i} />
        ))}
      </div>
      {hidden > 0 && (
        <button type="button" className="rv2-band-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : moreLabel(band, hidden)}
        </button>
      )}
    </>
  );

  if (!band.title) return <div className="rv2-band">{body}</div>;
  return (
    <section className="rv2-band" aria-labelledby={id}>
      <div className="rv2-band-head">
        <h2 id={id} className="rv2-band-title">{band.title}</h2>
        <span className="rv2-band-count">{places(band.results.length)}</span>
        <span className="rv2-band-rule" aria-hidden="true" />
      </div>
      {body}
    </section>
  );
}

/**
 * Open places by drive time (D13's bands): under 1 hour, 1–2 hours, …, then
 * boat-in places, which have no drive time to the site. Ranks for analytics
 * follow the order on screen.
 */
export function DriveBands({ results, params }: { results: CampgroundResult[]; params: SearchParams | null }) {
  const bands = groupByDriveBand(results);
  const starts = bands.map((_, i) => bands.slice(0, i).reduce((n, b) => n + b.results.length, 0));
  return (
    <div className="rv2-bands">
      {bands.map((b, i) => <Band key={b.key} band={b} params={params} firstRank={starts[i]} />)}
    </div>
  );
}
