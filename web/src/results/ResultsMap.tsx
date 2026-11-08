import { useEffect, useMemo, useRef } from "react";
import L from "../leaflet-setup";
import "leaflet.markercluster";
import type { CampgroundResult } from "../api";
import { pinLabel, pinLegend, pinStyle, pinSvg } from "./pins";
import { tileLayerConfig, type Theme } from "./tiles";
import "./ResultsMap.css";

// markerClusterGroup itself is declared in pages/MapView.tsx.
declare module "leaflet" {
  interface MarkerCluster extends Marker {
    getChildCount(): number;
    zoomToBounds(): void;
  }
}

const PNW_CENTER: L.LatLngExpression = [47.3, -121.0];
const MAPBOX_TOKEN: string | undefined = import.meta.env.VITE_PUBLIC_MAPBOX_TOKEN;

const currentTheme = (): Theme => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function pinIcon(r: CampgroundResult): L.DivIcon {
  const style = pinStyle(r);
  // Open pins are buttons named by their text; muted ones are scenery.
  const name = style.muted ? "" : `<span class="sr-only">${escapeHtml(pinLabel(r))}</span>`;
  return L.divIcon({
    className: `rv2-marker${style.muted ? " rv2-marker--muted" : ""}`,
    html: pinSvg(style) + name,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

function clusterIcon(cluster: L.MarkerCluster): L.DivIcon {
  const n = cluster.getChildCount();
  return L.divIcon({
    className: "rv2-cluster",
    html: `<span>${n}</span><span class="sr-only"> places, zoom in</span>`,
    iconSize: [36, 36],
  });
}

const hasCoords = (r: CampgroundResult) => !!r.latitude && !!r.longitude;

interface Props {
  /** Open places in list order, then places with nothing to book. */
  places: CampgroundResult[];
  /** Changes when a new search starts, so the map refits to its results. */
  searchKey: unknown;
}

/**
 * The results map beside the list (D13, desktop only). Lazy: Leaflet loads
 * with this chunk. The list on the left has the same places, so the map adds
 * where, not what.
 */
export default function ResultsMap({ places, searchKey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const clusterRef = useRef<L.MarkerClusterGroup | null>(null);
  // The user moved the map since this search started: stop refitting.
  const movedRef = useRef(false);
  const fittingRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { center: PNW_CENTER, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(map);
    const config = () => tileLayerConfig(MAPBOX_TOKEN, currentTheme());
    const first = config();
    const tiles = L.tileLayer(first.url, first.options).addTo(map);
    containerRef.current.classList.add(`rv2-map--${first.provider}`);
    // Swap the Mapbox style when the theme changes (OSM is restyled in CSS).
    const themeWatch = new MutationObserver(() => tiles.setUrl(config().url));
    if (first.provider === "mapbox") {
      themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    }
    map.on("movestart", () => {
      if (!fittingRef.current) movedRef.current = true;
    });
    map.on("moveend", () => { fittingRef.current = false; });
    const cluster = L.markerClusterGroup({
      // Cluster only pins that would overlap, and never once zoomed in.
      maxClusterRadius: 20,
      disableClusteringAtZoom: 10,
      showCoverageOnHover: false,
      iconCreateFunction: clusterIcon,
    });
    cluster.on("clusterkeydown", (e: L.LeafletEvent) => {
      const key = (e as L.LeafletKeyboardEvent).originalEvent.key;
      if (key === "Enter" || key === " ") (e as L.LeafletEvent & { layer: L.MarkerCluster }).layer.zoomToBounds();
    });
    map.addLayer(cluster);
    // The aside resizes with the window and the sticky height.
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(containerRef.current);
    mapRef.current = map;
    clusterRef.current = cluster;
    return () => {
      themeWatch.disconnect();
      resize.disconnect();
      map.remove();
      mapRef.current = null;
      clusterRef.current = null;
    };
  }, []);

  useEffect(() => {
    movedRef.current = false;
  }, [searchKey]);

  useEffect(() => {
    const map = mapRef.current;
    const cluster = clusterRef.current;
    if (!map || !cluster) return;
    cluster.clearLayers();
    const shown = places.filter(hasCoords);
    for (const r of shown) {
      const muted = r.total_available_sites <= 0;
      const marker = L.marker([r.latitude, r.longitude], {
        icon: pinIcon(r),
        interactive: !muted,
        keyboard: !muted,
        zIndexOffset: muted ? -1000 : 0,
      });
      if (!muted) marker.bindTooltip(escapeHtml(r.name), { direction: "top", offset: [0, -12] });
      cluster.addLayer(marker);
    }
    if (shown.length && !movedRef.current) {
      fittingRef.current = true;
      map.fitBounds(L.latLngBounds(shown.map((r) => [r.latitude, r.longitude] as L.LatLngTuple)),
        { padding: [48, 48], maxZoom: 11, animate: false });
      fittingRef.current = false;
    }
  }, [places]);

  const legend = useMemo(() => pinLegend(places.filter(hasCoords).map(pinStyle)), [places]);

  return (
    <div className="rv2-map">
      <div ref={containerRef} className="rv2-map-canvas" />
      {legend.length > 0 && (
        <div className="rv2-map-legend">
          <p className="rv2-map-legend-title">Key</p>
          <ul>
            {legend.map((e) => (
              <li key={e.text}>
                <span className="rv2-map-legend-pin" dangerouslySetInnerHTML={{ __html: pinSvg(e.style) }} />
                {e.text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
