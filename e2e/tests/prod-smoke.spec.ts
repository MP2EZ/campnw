import { test, expect } from "@playwright/test";

/**
 * Production synthetic monitor — READ-ONLY smoke.
 *
 * Runs against the LIVE site (E2E_BASE_URL=https://campable.co) on a daily
 * schedule via .github/workflows/prod-monitor.yml. Unlike the four flows in
 * this directory, it performs ZERO mutations: no signup, no Stripe, no
 * POST/DELETE. It only loads anonymous pages and reads the public search API,
 * so it is safe to point at production.
 *
 * Purpose: catch feature regressions on prod (broken homepage, dead search
 * pipeline, missing pricing/SEO pages) that the staging release-gate nightly
 * cannot see, and that PostHog only surfaces after a real user is harmed.
 */

// Compute future dates at runtime so the search query never goes stale.
function isoDate(daysFromNow: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + daysFromNow);
  return d.toISOString().slice(0, 10);
}

test("homepage renders core discovery UI", async ({ page }) => {
  await page.goto("/");

  // The discovery-mode tab switcher (Find a Site / Plan a Trip).
  await expect(
    page.getByRole("tablist", { name: "Discovery mode" })
  ).toBeVisible();

  // The structured search form — the app's primary surface.
  await expect(page.locator(".search-form")).toBeVisible();

  // Anonymous header CTA confirms auth wiring rendered.
  await expect(
    page.getByRole("button", { name: "Sign in" }).first()
  ).toBeVisible();
});

test("search API returns a valid response (DB + provider pipeline)", async ({
  request,
}) => {
  // The differentiator: a real availability search across the registry.
  // We assert the endpoint is healthy and well-shaped — NOT that any site is
  // available (external booking systems may legitimately have zero), to avoid
  // false alarms from upstream providers.
  const res = await request.get("/api/search", {
    params: {
      start_date: isoDate(30),
      end_date: isoDate(33),
      state: "WA",
      nights: "2",
      limit: "5",
    },
    timeout: 60_000,
  });

  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(typeof body.campgrounds_checked).toBe("number");
  expect(body.campgrounds_checked).toBeGreaterThan(0);
});

test("pricing page renders", async ({ page }) => {
  await page.goto("/pricing");
  await expect(
    page.getByRole("heading", { name: /pricing/i, level: 1 })
  ).toBeVisible();
  // Both plan cards render. We assert structure, not the CTA: the CTA is
  // auth-dependent (anon sees "Sign in to upgrade", free sees "Upgrade to
  // Pro") and we stay logged-out / never click it (would hit Stripe).
  await expect(page.locator(".pricing-card-free")).toBeVisible();
  await expect(page.locator(".pricing-card-pro")).toBeVisible();
});

test("SEO state index renders", async ({ page }) => {
  const res = await page.goto("/campgrounds/wa");
  expect(res?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
