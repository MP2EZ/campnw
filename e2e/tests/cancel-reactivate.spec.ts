import { test, expect } from "@playwright/test";
import { signupFresh } from "../fixtures/auth";
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
  await page.getByRole("button", { name: "Upgrade to Pro" }).click({ force: true });
  await expect(page).toHaveURL(/checkout\.stripe\.com/, { timeout: 30_000 });
  await payWithCard(page);
  await waitForProBadge(page);

  // Step 2: open billing portal and cancel
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });

  await page.getByRole("button", { name: /Cancel plan/i }).click();
  await page.getByRole("button", { name: /Cancel subscription/i }).click();
  await expect(page.getByText(/Subscription canceled/i)).toBeVisible();

  // Step 3: back to campable — assert "Pro until <date>" copy
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 30_000 });

  // Step 4: reactivate via Portal
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });
  await page.getByRole("button", { name: /Renew plan/i }).click();
  await page.getByRole("button", { name: /Confirm/i }).click();

  // Step 5: back to campable — "Pro until" text should be gone
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeHidden({ timeout: 30_000 });
});
