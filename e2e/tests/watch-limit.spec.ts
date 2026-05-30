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

  // Use the structured search form (no name filter) so we get a broad
  // result set with actual per-campground Watch buttons. Default state
  // (Seattle/WA, ~30 days) reliably returns multiple results with
  // availability and per-result Watch buttons.
  await page.getByRole("button", { name: "Search", exact: true }).click();

  // Wait for results to load. Per-result "Watch" buttons appear when
  // at least one campground has availability.
  const watchBtn = page.getByRole("button", { name: "Watch", exact: true }).first();
  await watchBtn.waitFor({ state: "visible", timeout: 45_000 });
  await watchBtn.click({ force: true });

  // 402 → UpgradeModal with watch-limit headline
  await expect(page.getByRole("heading", { name: "Upgrade for unlimited watches" })).toBeVisible();
  await expect(page.getByText(/Free accounts can track 3 campgrounds/i)).toBeVisible();
});
