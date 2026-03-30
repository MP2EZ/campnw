import { useEffect, useRef, useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { useSearchContext } from "../contexts/SearchContext";
import type { CampgroundResult, SearchParams } from "../api";
import L from "../leaflet-setup";
import "leaflet.markercluster";
import "./MapView.css";

// Inline type augmentation for leaflet.markercluster
declare module "leaflet" {
  function markerClusterGroup(options?: Record<string, unknown>): L.MarkerClusterGroup;
  interface MarkerClusterGroup extends L.FeatureGroup {
    clearLayers(): this;
    addLayer(layer: L.Layer): this;
    getAllChildMarkers(): L.Marker[];
    zoomToShowLayer(layer: L.Layer, callback?: () => void): void;
  }
}

const PNW_CENTER: L.LatLngExpression = [47.3, -121.0];
const DEFAULT_ZOOM = 7;

const PIN_COLOR_TOKENS: Record<string, string> = {
  recgov: "--src-recgov-border",
  wa_state: "--src-wa-border",
  or_state: "--src-or-border",
  id_state: "--src-id-border",
};

const PIN_COLOR_FALLBACKS: Record<string, string> = {
  recgov: "#5a8a32",
  wa_state: "#3498b0",
  or_state: "#d4920a",
  id_state: "#7d3cb5",
};

function getPinColors(): Record<string, string> {
  const style = getComputedStyle(document.documentElement);
  const colors: Record<string, string> = {};
  for (const [key, token] of Object.entries(PIN_COLOR_TOKENS)) {
    const val = style.getPropertyValue(token).trim();
    colors[key] = val || PIN_COLOR_FALLBACKS[key];
  }
  return colors;
}

function pinRadius(totalSites: number): number {
  if (totalSites >= 11) return 14;
  if (totalSites >= 4) return 10;
  return 6;
}

function formatDrive(minutes: number | null): string {
  if (minutes === null) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `~${m}m`;
  if (m === 0) return `~${h}h`;
  return `~${h}h ${m}m`;
}

function popupHtml(r: CampgroundResult): string {
  const sourceLabels: Record<string, string> = { recgov: "Rec.gov", wa_state: "WA Parks", or_state: "OR Parks", id_state: "ID Parks" };
  const sourceLabel = sourceLabels[r.booking_system] || r.booking_system;
  const sourceClass = `source-${r.booking_system}`;
  const drive = r.estimated_drive_minutes ? ` · ${formatDrive(r.estimated_drive_minutes)} drive` : "";
  const link = r.availability_url
    ? `<a href="${r.availability_url}" target="_blank" rel="noopener">View availability ↗</a>`
    : "";
  return `
    <div class="map-popup">
      <strong>${r.name}</strong>
      <span class="source-badge ${sourceClass}">${sourceLabel}</span>
      <p>${r.total_available_sites} sites available${drive}</p>
      ${link}
    </div>
  `;
}

function clusterIcon(cluster: { getChildCount: () => number; getAllChildMarkers: () => L.Marker[] }): L.DivIcon {
  const count = cluster.getChildCount();
  let size = 30;
  let className = "cluster-sm";
  if (count >= 20) { size = 44; className = "cluster-lg"; }
  else if (count >= 5) { size = 36; className = "cluster-md"; }
  return L.divIcon({
    html: `<span>${count}</span>`,
    className: `map-cluster ${className}`,
    iconSize: L.point(size, size),
  });
}

function searchUrl(params: SearchParams): string {
  const url = new URL("/", window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "" && v !== false) {
      url.searchParams.set(k, String(v));
    }
  }
  return url.pathname + url.search;
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T12:00:00");
  const e = new Date(end + "T12:00:00");
  const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(s)} – ${fmt(e)}`;
}

export default function MapView() {
  const { filteredResults, loading, searchParams, searchDates } = useSearchContext();
  const location = useLocation();
  const focusId = new URLSearchParams(location.search).get("focus");
  const pinColors = useMemo(() => getPinColors(), []);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const clusterRef = useRef<L.MarkerClusterGroup | null>(null);
  const markerMap = useRef<Map<string, L.CircleMarker>>(new Map());

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: PNW_CENTER,
      zoom: DEFAULT_ZOOM,
      keyboard: true,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update markers when results change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (clusterRef.current) {
      map.removeLayer(clusterRef.current);
    }

    const withAvailability = filteredResults.filter((r) => r.total_available_sites > 0);
    if (!withAvailability.length) return;

    const cluster = L.markerClusterGroup({
      maxClusterRadius: 40,
      iconCreateFunction: clusterIcon,
    });

    const markers = new Map<string, L.CircleMarker>();
    for (const r of withAvailability) {
      if (!r.latitude || !r.longitude) continue;
      const color = pinColors[r.booking_system] || pinColors.recgov;
      const marker = L.circleMarker([r.latitude, r.longitude], {
        radius: pinRadius(r.total_available_sites),
        fillColor: color,
        fillOpacity: 0.85,
        color: color,
        weight: 2,
        opacity: 1,
      });
      marker.bindPopup(popupHtml(r), { maxWidth: 280 });
      cluster.addLayer(marker);
      markers.set(String(r.facility_id), marker);
    }

    map.addLayer(cluster);
    clusterRef.current = cluster;
    markerMap.current = markers;

    // Fit bounds to show all markers (skip if focusing on a specific one)
    if (withAvailability.length > 1 && !focusId) {
      const bounds = L.latLngBounds(
        withAvailability
          .filter((r) => r.latitude && r.longitude)
          .map((r) => [r.latitude, r.longitude] as L.LatLngTuple)
      );
      map.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [filteredResults, focusId, pinColors]);

  // Focus on a specific campground when ?focus=ID is in the URL
  // Uses location as dep so re-navigating to the same ID still triggers
  useEffect(() => {
    const map = mapRef.current;
    const cluster = clusterRef.current;
    if (!map || !cluster || !focusId || !markerMap.current.size) return;
    const marker = markerMap.current.get(focusId);
    if (!marker) return;
    // zoomToShowLayer unclusters the marker, then we open its popup
    setTimeout(() => {
      cluster.zoomToShowLayer(marker, () => {
        marker.openPopup();
      });
    }, 300);
  }, [location, filteredResults]); // eslint-disable-line react-hooks/exhaustive-deps

  const withAvailability = filteredResults.filter((r) => r.total_available_sites > 0);

  const summaryParts = useMemo(() => {
    if (!searchParams || !searchDates) return null;
    const parts: string[] = [formatDateRange(searchDates.start, searchDates.end)];
    if (searchParams.nights && searchParams.nights > 1) parts.push(`${searchParams.nights} nights`);
    if (searchParams.state) parts.push(searchParams.state);
    if (searchParams.from_location) parts.push(`from ${searchParams.from_location}`);
    if (searchParams.max_drive) parts.push(`≤${Math.floor(searchParams.max_drive / 60)}hr`);
    if (searchParams.name) parts.push(`"${searchParams.name}"`);
    return { text: parts.join(" · "), editUrl: searchUrl(searchParams) };
  }, [searchParams, searchDates]);

  if (!filteredResults.length && !loading) {
    return (
      <main id="main-content" className="map-empty">
        <h2>No search results yet</h2>
        <p>Run a search to see campgrounds on the map.</p>
        <Link to="/" className="header-btn active">Go to Search</Link>
      </main>
    );
  }

  return (
    <main id="main-content" className="map-page">
      <div aria-live="polite" className="sr-only">
        {loading ? "Loading map results" : `Map showing ${withAvailability.length} campgrounds with availability`}
      </div>
      {summaryParts && (
        <div className="map-summary-bar">
          <span className="map-summary-text">
            {summaryParts.text} · {withAvailability.length} with availability
          </span>
          <Link to={summaryParts.editUrl} className="map-summary-edit">Edit search</Link>
        </div>
      )}
      <div
        ref={containerRef}
        className="map-container"
        role="application"
        aria-label={`Campground map showing ${withAvailability.length} results`}
      />
      {withAvailability.length > 0 && (
        <details className="map-list-alt">
          <summary>View as list ({withAvailability.length} campgrounds)</summary>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Source</th>
                <th>Sites</th>
                <th>Drive</th>
              </tr>
            </thead>
            <tbody>
              {withAvailability.map((r) => (
                <tr key={r.facility_id}>
                  <td>
                    {r.availability_url ? (
                      <a href={r.availability_url} target="_blank" rel="noopener">{r.name}</a>
                    ) : r.name}
                  </td>
                  <td>{{ recgov: "Rec.gov", wa_state: "WA Parks", or_state: "OR Parks", id_state: "ID Parks" }[r.booking_system] || r.booking_system}</td>
                  <td>{r.total_available_sites}</td>
                  <td>{formatDrive(r.estimated_drive_minutes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </main>
  );
}
