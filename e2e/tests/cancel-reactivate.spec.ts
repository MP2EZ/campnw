import { test, expect } from "@playwright/test";
import { signupFresh, skipOnboarding } from "../fixtures/auth";
import { payWithCard, waitForProBadge } from "../fixtures/stripe";

/**
 * Flow 4 — Cancel + reactivate via Stripe Customer Portal.
 *
 * Originally planned to use a pre-seeded Pro fixture user, but creating
 * a real Stripe customer + subscription in the seed step took 9+ min
 * (likely Stripe API throttling on Customer.list against accumulated
 * test customers). Instead this test does its own signup + upgrade
 * first (same path as the smoke flow), then exercises the
 * cancel-reactivate loop.
 *
 * Trade-off: ~30s longer per run, but fully deterministic and no
 * fixture-creation gymnastics.
 *
 * Total runtime: ~60-90s.
 */
test("New Pro user can cancel and reactivate via Customer Portal", async ({ page }) => {
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

  // Stripe Portal cancel flow. The "Cancel subscription" element may
  // be an <a> styled as a button OR a <button>; use generic text match.
  // First click opens a confirmation page; second click confirms.
  await page.getByText("Cancel subscription", { exact: true }).first().click();
  await page.getByText("Cancel subscription", { exact: true }).last().click();
  // Stripe Portal confirms with "Subscription has been canceled" or
  // similar. Match any phrasing that includes "canceled".
  await expect(page.getByText(/cance(l|ll)ed/i).first()).toBeVisible({ timeout: 15_000 });

  // Step 3: back to campable — assert "Pro until <date>" copy
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 30_000 });

  // Step 4: reactivate via Portal
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });
  // Stripe Portal reactivation: a single click usually fires the
  // mutation directly (button changes to 'Renewing…' loading state).
  // No confirmation modal needed in the modern Portal.
  await page.getByText(/(Renew|Reactivate|Resume|Don.t cancel|Continue your)/i).first().click();

  // Step 5: back to campable — "Pro until" text should be gone
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeHidden({ timeout: 30_000 });
});
