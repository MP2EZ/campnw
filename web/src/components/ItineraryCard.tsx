import { memo } from "react";
import { track } from "../api";
import { SaveToTripButton } from "./SaveToTripButton";

export interface ItineraryLeg {
  name: string;
  facility_id: string;
  booking_system: string;
  dates: string;
  nights: number;
  drive_minutes: number;
  sites_available: number;
  booking_url: string;
  tags: string[];
}

function formatDrive(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export const ItineraryCard = memo(function ItineraryCard({ leg, index }: { leg: ItineraryLeg; index: number }) {
  const sourceClass = leg.booking_system === "wa_state" ? "wa_state"
    : leg.booking_system === "or_state" ? "or_state" : "recgov";

  return (
    <div className="itinerary-card">
      <div className="itinerary-card-index">{index + 1}</div>
      <div className="itinerary-card-body">
        <div className="itinerary-card-header">
          <h4 className="itinerary-card-name">{leg.name}</h4>
          <span className={`source-badge source-${sourceClass}`}>
            {leg.booking_system === "wa_state" ? "WA Parks"
              : leg.booking_system === "or_state" ? "OR Parks" : "Rec.gov"}
          </span>
        </div>
        <div className="itinerary-card-details">
          <span className="itinerary-card-dates">{leg.dates}</span>
          {leg.nights > 0 && <span className="itinerary-card-nights">{leg.nights} night{leg.nights !== 1 ? "s" : ""}</span>}
          <span className="itinerary-card-drive">~{formatDrive(leg.drive_minutes)}</span>
          <span className="itinerary-card-sites">{leg.sites_available} site{leg.sites_available !== 1 ? "s" : ""}</span>
        </div>
        {leg.tags.length > 0 && (
          <div className="itinerary-card-tags">
            {leg.tags.slice(0, 4).map(t => <span key={t} className="itinerary-tag">{t}</span>)}
          </div>
        )}
        {leg.booking_url && (
          <div className="itinerary-card-actions">
            <a
              href={leg.booking_url}
              target="_blank"
              rel="noopener"
              className="itinerary-card-book"
              onClick={() => track("book_click", {
                facility_id: leg.facility_id,
                name: leg.name,
                source: leg.booking_system,
                type: "itinerary",
                leg_index: index,
              })}
            >
              Book
            </a>
            <SaveToTripButton
              facilityId={leg.facility_id}
              source={leg.booking_system}
              name={leg.name}
            />
          </div>
        )}
      </div>
    </div>
  );
});

/** Parse itinerary JSON from a markdown code fence in the message content. */
export function parseItinerary(content: string): ItineraryLeg[] | null {
  const match = content.match(/```itinerary\s*\n([\s\S]*?)```/);
  if (!match) return null;
  try {
    const legs = JSON.parse(match[1]);
    if (Array.isArray(legs) && legs.length > 0 && legs[0].name) return legs;
  } catch { /* ignore parse errors */ }
  return null;
}
