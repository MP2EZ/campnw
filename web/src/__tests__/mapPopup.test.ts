import { describe, expect, test } from "vitest";
import type { CampgroundResult } from "../api";
import { escapeHtml, mapPopupHtml } from "../lib/mapPopup";

const base = {
  name: "Lake Camp",
  booking_system: "recgov",
  total_available_sites: 3,
  estimated_drive_minutes: 90,
  availability_url: "https://www.recreation.gov/camping/campgrounds/1",
} as unknown as CampgroundResult;

describe("mapPopupHtml (SEC-14)", () => {
  test("escapes a campground name from upstream data", () => {
    const html = mapPopupHtml({ ...base, name: '<img src=x onerror="alert(1)">' });
    expect(html).not.toContain("<img");
    expect(html).toContain("&#60;img");
  });

  test("keeps an https availability link", () => {
    expect(mapPopupHtml(base)).toContain(
      'href="https://www.recreation.gov/camping/campgrounds/1"',
    );
  });

  test("drops a non-https link and escapes quotes in the href", () => {
    expect(mapPopupHtml({ ...base, availability_url: "javascript:alert(1)" })).not.toContain("href=");
    const quoted = mapPopupHtml({ ...base, availability_url: 'https://x.test/"onmouseover="a' });
    expect(quoted).not.toContain('"onmouseover="');
  });

  test("escapeHtml covers the five HTML metacharacters", () => {
    expect(escapeHtml(`&<>"'`)).toBe("&#38;&#60;&#62;&#34;&#39;");
  });
});
