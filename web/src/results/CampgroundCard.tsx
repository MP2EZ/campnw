import { memo } from "react";
import { track, type CampgroundResult, type SearchParams } from "../api";
import { formatDriveTime, parseIsoDate } from "../lib/dates";
import { SOURCE_NAMES } from "../lib/sources";
import { IconBoat, IconClock, IconSun, IconTent } from "../icons";
import { buildWindowChips, type WindowChip } from "./chips";
import { fitLine, NOT_LISTED } from "./fit";
import { PlaceThumb } from "./PlaceThumb";
import { useCardSelection } from "./selection";
import { WindowChips } from "./WindowChips";

interface Props {
  result: CampgroundResult;
  params: SearchParams | null;
  rank: number;
}

/**
 * "Mid-June 67° / 50°". The temperatures are normals for the middle of the
 * searched range (the backend picks that date), so the label names it.
 */
function weatherLabel(r: CampgroundResult, p: SearchParams | null): string | null {
  const hi = r.weather_temp_high_f;
  const lo = r.weather_temp_low_f;
  if (hi == null || hi <= -900 || lo == null || !p?.start_date || !p.end_date) return null;
  const s = parseIsoDate(p.start_date);
  const span = Math.round((parseIsoDate(p.end_date).getTime() - s.getTime()) / 86_400_000);
  s.setDate(s.getDate() + Math.floor(span / 2));
  const part = s.getDate() <= 10 ? "Early" : s.getDate() <= 20 ? "Mid" : "Late";
  const rain = (r.weather_precip_pct ?? 0) >= 20 ? ` · ${r.weather_precip_pct}% rain` : "";
  return `${part}-${s.toLocaleDateString("en-US", { month: "long" })} ${Math.round(hi)}° / ${Math.round(lo)}°${rain}`;
}

/** A place with open stays: where it is, what fits, and the stays to book. */
export const CampgroundCard = memo(function CampgroundCard({ result, params, rank }: Props) {
  const source = SOURCE_NAMES[result.booking_system] ?? result.booking_system;
  const id = `rv2-card-${result.facility_id}`;
  const weather = weatherLabel(result, params);
  const tags = (result.tags ?? []).filter((t) => t !== "boat-in");
  const fit = fitLine(result.windows);
  const onBook = (chip: WindowChip) => track("book_click", {
    facility_id: result.facility_id,
    result_rank: rank,
    drive_minutes: result.estimated_drive_minutes ?? -1,
    total_available_sites: result.total_available_sites,
    name: result.name,
    source: result.booking_system,
    type: "window_chip",
    sites_in_chip: chip.open,
    has_photo: result.image_urls?.length ? 1 : 0,
  });

  const { selected, ...selection } = useCardSelection(result.facility_id);

  return (
    <article className={selected ? "rv2-card is-selected" : "rv2-card"} aria-labelledby={id} {...selection}>
      <PlaceThumb result={result} />
      <div className="rv2-card-head">
        <h3 id={id} className="rv2-card-name" tabIndex={-1}>{result.name}</h3>
        <p className="rv2-card-meta">
          {result.boat_in ? (
            <span className="rv2-boat"><IconBoat className="rv2-icon" />Boat-in only</span>
          ) : result.estimated_drive_minutes != null && (
            <span className="rv2-drive">
              <IconClock className="rv2-icon" />{formatDriveTime(result.estimated_drive_minutes)} drive
            </span>
          )}
          {result.region && <span>{result.region}</span>}
          {weather && (
            <span className="rv2-meta-item">
              <IconSun className="rv2-icon" /><span className="sr-only">Typical weather: </span>{weather}
            </span>
          )}
        </p>
      </div>
      <div className="rv2-card-main">
        {result.elevator_pitch && <p className="rv2-card-pitch">{result.elevator_pitch}</p>}
        <p className="rv2-card-fit">
          <span className={fit === NOT_LISTED ? "rv2-fit rv2-card-muted" : "rv2-fit"}>
            <IconTent className="rv2-icon" />{fit}
          </span>
          <span className="rv2-card-muted">Book via {source}</span>
          {result.fcfs_sites > 0 && (
            <span className="rv2-card-muted">+ {result.fcfs_sites} first-come, first-served site{result.fcfs_sites === 1 ? "" : "s"}</span>
          )}
        </p>
        <WindowChips
          chips={buildWindowChips(result, params)}
          name={result.name}
          params={params}
          source={source}
          onBook={onBook}
        />
        {tags.length > 0 && <p className="rv2-card-tags">{tags.join(" · ")}</p>}
      </div>
    </article>
  );
});
