import { test, expect } from "@playwright/test";
import { signupFresh, skipOnboarding } from "../fixtures/auth";
import { payWithCard, waitForProBadge } from "../fixtures/stripe";

/**
 * Flow 4 — Cancel via Stripe Customer Portal.
 *
 * Validates the cancel half of the cancel/reactivate loop:
 *   signup → upgrade → cancel via Portal → "Pro until <date>" appears
 *
 * Why no reactivate assertion: Stripe Portal's reactivate UI varies
 * (button text, multi-step confirmation modals), webhook delivery
 * timing varies, and end-to-end "Pro until disappears" depends on
 * a Stripe → webhook → DB → BillingProvider chain that can take
 * 30-60+ seconds. The CANCEL half exercises exactly the same chain
 * (subscription.updated webhook fires for both cancel and reactivate)
 * and is the high-value assertion for v1.41.
 *
 * Total runtime: ~60-90s.
 */
test("New Pro user can cancel via Customer Portal", async ({ page }) => {
  test.setTimeout(120_000);

  // Step 1: signup + upgrade (same as smoke flow)
  await signupFresh(page, { displayName: "E2E Cancel" });
  await page.goto("/pricing");
  await skipOnboarding(page);
  await page.getByRole("button", { name: "Upgrade to Pro" }).click({ force: true });
  await expect(page).toHaveURL(/checkout\.stripe\.com/, { timeout: 30_000 });
  await payWithCard(page);
  await waitForProBadge(page);

  // Step 2: open billing portal and cancel
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });

  // Stripe Portal cancel flow: first click navigates to confirmation
  // page; second click confirms the cancellation.
  await page.getByText("Cancel subscription", { exact: true }).first().click();
  await page.getByText("Cancel subscription", { exact: true }).last().click();
  // Stripe confirms with "Subscription has been canceled" or similar.
  await expect(page.getByText(/cance(l|ll)ed/i).first()).toBeVisible({ timeout: 15_000 });

  // Step 3: back to campable — webhook → DB → UI loop validation
  // "Pro until <date>" should appear in BillingSettings.
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 30_000 });
});
