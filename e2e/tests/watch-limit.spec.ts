import { test, expect } from "@playwright/test";
import { loginAsFixture, skipOnboarding } from "../fixtures/auth";

/**
 * Flow 2 — Watch limit enforcement.
 *
 * Pre-seeded free user has 3 active watches. 4th watch creation must
 * fire HTTP 402 and open UpgradeModal with reason=watch_limit.
 *
 * Requires fixture: e2e-fixture-free-3watches@maestro.test
 * (seeded by scripts/seed_e2e_fixtures.py)
 */
test("4th watch attempt opens UpgradeModal with watch_limit copy", async ({ page }) => {
  await loginAsFixture(page, "free-3watches");
  // skipOnboarding called inside loginAsFixture; call again in case the
  // modal re-appears after some action on the landing page.
  await skipOnboarding(page);

  // Use the structured search form's name filter — bypasses the
  // natural-language search path (which requires ANTHROPIC_API_KEY,
  // not always set on staging).
  await page.getByRole("textbox", { name: "Campground name filter" }).fill("Ohanapecosh");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  // Wait until the search has completed (the "Checked N campgrounds"
  // status appears regardless of whether results came back).
  await expect(page.getByText(/Checked \d+ campground/i)).toBeVisible({ timeout: 30_000 });

  // Use the "Watch this search" CTA which creates a watch from the
  // search params themselves — works even when search returned 0
  // matching availability (Ohanapecosh often has 0 free sites). The
  // backend's watch-creation 402 fires regardless of how the watch
  // was constructed.
  await page.getByRole("button", { name: "Watch this search" }).click({ force: true });

  // 402 → UpgradeModal with watch-limit headline
  await expect(page.getByRole("heading", { name: "Upgrade for unlimited watches" })).toBeVisible();
  await expect(page.getByText(/Free accounts can track 3 campgrounds/i)).toBeVisible();
});
