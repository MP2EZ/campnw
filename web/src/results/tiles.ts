export type Theme = "light" | "dark";

export interface TileLayerConfig {
  provider: "mapbox" | "osm";
  url: string;
  options: { attribution: string; maxZoom: number; tileSize?: number; zoomOffset?: number };
}

const OSM_CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const MAPBOX_STYLES: Record<Theme, string> = { light: "light-v11", dark: "dark-v11" };

/**
 * Map tiles (D13). A public Mapbox token (VITE_PUBLIC_MAPBOX_TOKEN, baked in
 * at build time) gets a Mapbox style per theme. Without one, OpenStreetMap's
 * tiles, which results-map CSS tones down to fit the palette.
 */
export function tileLayerConfig(token: string | undefined, theme: Theme): TileLayerConfig {
  const t = token?.trim();
  if (!t) {
    return {
      provider: "osm",
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      options: { attribution: OSM_CREDIT, maxZoom: 18 },
    };
  }
  return {
    provider: "mapbox",
    url: `https://api.mapbox.com/styles/v1/mapbox/${MAPBOX_STYLES[theme]}/tiles/512/{z}/{x}/{y}{r}?access_token=${t}`,
    options: {
      attribution: `&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> ${OSM_CREDIT} `
        + '<a href="https://www.mapbox.com/map-feedback/">Improve this map</a>',
      maxZoom: 18,
      tileSize: 512,
      zoomOffset: -1,
    },
  };
}
