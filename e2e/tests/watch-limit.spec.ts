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
  await skipOnboarding(page);

  // Run a plain-language search likely to surface a fresh campground
  // (one whose facility_id is NOT in the fixture's 3 seeded watches).
  const nlSearch = page.getByPlaceholder(/pet-friendly/i);
  await nlSearch.fill("Ohanapecosh");
  await nlSearch.press("Enter");

  // First result with a Watch button → click → modal opens
  await expect(page.getByText(/Ohanapecosh/i).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Watch" }).first().click();

  // 402 → UpgradeModal with watch-limit headline
  await expect(page.getByRole("heading", { name: "Upgrade for unlimited watches" })).toBeVisible();
  await expect(page.getByText(/Free accounts can track 3 campgrounds/i)).toBeVisible();
});
