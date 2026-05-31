import { test, expect } from "@playwright/test";
import { loginAsFixture, skipOnboarding } from "../fixtures/auth";

/**
 * Flow 3 — Trip planner session limit enforcement.
 *
 * Pre-seeded free user has 3 planner sessions this month. 4th attempt
 * must fire HTTP 402 and open UpgradeModal with reason=planner_limit.
 *
 * Requires fixture: e2e-fixture-free-3planner@maestro.test
 */
test("4th planner session opens UpgradeModal with planner_limit copy", async ({ page }) => {
  await loginAsFixture(page, "free-3planner");
  await skipOnboarding(page);

  await page.goto("/plan");
  const input = page.locator("#chat-input");
  await input.fill("Find me a lakeside spot near Seattle next weekend");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(
    page.getByRole("heading", { name: "Upgrade for more trip planner sessions" }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Free accounts get 3 trip planner sessions per month/i)).toBeVisible();
});
