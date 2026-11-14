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

// Weekends seven to eight months out: past Recreation.gov's six-month
// release, so every federal place there offers "Remind me", and the busy
// ones also offer "Watch" on full weekends. Both count toward the limit.
function isoDate(daysFromNow: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + daysFromNow);
  return d.toISOString().slice(0, 10);
}

test("4th watch attempt opens UpgradeModal with watch_limit copy", async ({ page }) => {
  await loginAsFixture(page, "free-3watches");
  const search = new URLSearchParams({
    start_date: isoDate(210),
    end_date: isoDate(240),
    nights: "2",
    days_of_week: "4,5,6",
    from_location: "seattle",
    max_drive: "180",
    state: "WA",
  });
  await page.goto(`/?${search}`);
  // skipOnboarding again in case the modal re-appears after the reload.
  await skipOnboarding(page);

  // A card's full or not-released chip, or a row in the "Full or not
  // released yet" group, opens the Watch sheet.
  const action = page.getByRole("button", { name: /^(Watch|Remind me): / })
    .or(page.locator(".rv2-chip-watch"))
    .first();
  await action.waitFor({ state: "visible", timeout: 60_000 });
  await action.click();

  await page.getByRole("button", { name: /^(Start watching|Remind me on)/ }).click();

  // 402 → UpgradeModal with watch-limit headline
  await expect(page.getByRole("heading", { name: "Upgrade for unlimited watches" })).toBeVisible();
  await expect(page.getByText(/Free accounts can track 3 campgrounds/i)).toBeVisible();
});
