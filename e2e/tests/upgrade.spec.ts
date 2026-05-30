import { test, expect } from "@playwright/test";
import { signupFresh, skipOnboarding } from "../fixtures/auth";
import { payWithCard, waitForProBadge } from "../fixtures/stripe";

/**
 * Flow 1 — Hero smoke test.
 *
 * Anonymous → signup → /pricing → Upgrade to Pro → Stripe Checkout
 * (test card 4242…) → assert PRO badge in header.
 *
 * Catches 4 of the 5 production bug classes hit during v1.4 validation
 * (env vars at build, CSP scheme, modal width regression, useAuth race).
 */
test("anonymous signup → upgrade → assert PRO badge", async ({ page }) => {
  await signupFresh(page, { displayName: "E2E Smoke" });

  // Onboarding modal appears on first navigation post-signup — dismiss
  // it AFTER goto so the page has actually rendered the modal.
  await page.goto("/pricing");
  await skipOnboarding(page);

  await page.getByRole("button", { name: "Upgrade to Pro" }).click();

  // Stripe Checkout redirect — wait for the Checkout origin
  await expect(page).toHaveURL(/checkout\.stripe\.com/, { timeout: 30_000 });

  await payWithCard(page);

  // Stripe redirects back to campable with ?billing=success;
  // BillingProvider strips the param + flips state to pro via webhook.
  await waitForProBadge(page);
});
