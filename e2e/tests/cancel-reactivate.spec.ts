import { test, expect } from "@playwright/test";
import { loginAsFixture, skipOnboarding } from "../fixtures/auth";

/**
 * Flow 4 — Cancel + reactivate via Stripe Customer Portal.
 *
 * Pre-seeded Pro user → Manage billing → Stripe Portal → Cancel →
 * assert "Pro until <date>" copy renders in BillingSettings →
 * Manage billing again → Reactivate → assert "Pro until …" copy gone.
 *
 * Validates the webhook → DB → UI roundtrip end-to-end.
 *
 * Requires fixture: e2e-fixture-pro@maestro.test with an active
 * Stripe test-mode subscription.
 */
test("Pro user can cancel and reactivate via Customer Portal", async ({ page }) => {
  await loginAsFixture(page, "pro");
  await skipOnboarding(page);

  // Pro badge confirms login + Pro state
  await expect(page.locator(".pro-badge").first()).toBeVisible();

  // UserMenu → Billing → Manage billing → Stripe Customer Portal
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await page.getByRole("button", { name: "Manage billing" }).click();

  // Customer Portal: Cancel flow
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });
  await page.getByRole("button", { name: /Cancel plan/i }).click();
  await page.getByRole("button", { name: /Cancel subscription/i }).click();
  await expect(page.getByText(/Subscription canceled/i)).toBeVisible();

  // Back to campable — BillingSettings now shows "Pro until <localized date>"
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 30_000 });

  // Reactivate via Portal
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL(/billing\.stripe\.com/, { timeout: 30_000 });
  await page.getByRole("button", { name: /Renew plan/i }).click();
  await page.getByRole("button", { name: /Confirm/i }).click();

  // Back to campable — "Pro until" text should be gone
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeHidden({ timeout: 30_000 });
});
