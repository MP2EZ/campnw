import type { CampgroundResult, SearchParams } from "../api";
import { quickPicks } from "./picks";

/**
 * Three ways into the results (design: Main.dc.html "Quick picks"). Each
 * jumps to its card, opening its drive band if the card was folded away.
 * Hidden with fewer than two picks: one pick isn't a choice.
 */
export function QuickPicks({ results, params, onPick }: {
  results: CampgroundResult[];
  params: SearchParams | null;
  onPick: (facilityId: string) => void;
}) {
  const picks = quickPicks(results, params);
  if (picks.length < 2) return null;
  return (
    <section className="rv2-picks" aria-labelledby="rv2-picks-h">
      <h2 id="rv2-picks-h" className="rv2-picks-title">Quick picks</h2>
      <ul className="rv2-picks-grid">
        {picks.map((p) => (
          <li key={p.kicker}>
            <a className="rv2-pick" href={`#rv2-card-${p.result.facility_id}`}
              onClick={(e) => { e.preventDefault(); onPick(p.result.facility_id); }}>
              {/* Spaces between the parts keep the link's name readable; flex hides them. */}
              <span className="rv2-pick-kicker">{p.kicker}</span>{" "}
              <span className="rv2-pick-name">{p.result.name}</span>{" "}
              <span className="rv2-pick-detail">{p.detail}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
