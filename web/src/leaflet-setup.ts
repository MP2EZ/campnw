/**
 * Leaflet setup module — globalizes L before plugins (e.g. markercluster) load.
 * UMD plugins expect window.L to exist at import time.
 */
import L from "leaflet";
import "leaflet/dist/leaflet.css";

(window as unknown as Record<string, unknown>).L = L;

export default L;
