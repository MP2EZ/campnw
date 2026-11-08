import { describe, test, expect } from "vitest";
import { tileLayerConfig } from "../results/tiles";

describe("tileLayerConfig", () => {
  test("with a Mapbox token, uses the light or dark Mapbox style for the theme", () => {
    const light = tileLayerConfig("pk.abc", "light");
    const dark = tileLayerConfig("pk.abc", "dark");
    expect(light.provider).toBe("mapbox");
    expect(light.url).toMatch(/^https:\/\/api\.mapbox\.com\/styles\/v1\/mapbox\/[\w-]+\/tiles\/512\/\{z\}\/\{x\}\/\{y\}\{r\}\?access_token=pk\.abc$/);
    expect(dark.url).not.toBe(light.url);
    expect(light.options).toMatchObject({ tileSize: 512, zoomOffset: -1 });
    expect(light.options.attribution).toContain("Mapbox");
    expect(light.options.attribution).toContain("OpenStreetMap");
  });

  test("without a token, falls back to OpenStreetMap tiles (restyled in CSS)", () => {
    for (const token of [undefined, "", "  "]) {
      const c = tileLayerConfig(token, "dark");
      expect(c.provider).toBe("osm");
      expect(c.url).toBe("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
      expect(c.options.attribution).toContain("OpenStreetMap");
    }
  });
});
