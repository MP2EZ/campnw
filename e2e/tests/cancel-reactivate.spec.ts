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
 * Total runtime: ~90-150s.
 */
test("New Pro user can cancel via Customer Portal", async ({ page }) => {
  test.setTimeout(180_000);

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

  // Stripe Portal cancel flow, as of 2026-08:
  //   portal home → "Cancel subscription"
  //   → "Confirm cancellation" page → "Cancel subscription"
  //   → "Cancel your subscription" survey modal → "Continue to cancellation"
  //
  // Deliberately no ordinal locators (.first()/.last()) past the first step.
  // The modal renders the confirm page's button underneath it, still visible
  // and enabled but pointer-blocked by Stripe's overlay layer, so ordinals
  // silently re-bind to an unclickable node.
  await page.getByText("Cancel subscription", { exact: true }).first().click();

  await expect(page.getByText("Confirm cancellation")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Cancel subscription" }).click();

  // The reason survey is a Portal setting Stripe can toggle, so treat it as
  // optional rather than letting its absence fail the run. The reason select
  // itself is optional — "Continue to cancellation" is enabled without it.
  const survey = page.getByRole("alertdialog", { name: /cancel your subscription/i });
  const surveyAppeared = await survey
    .waitFor({ state: "visible", timeout: 10_000 })
    .then(() => true, () => false);
  if (surveyAppeared) {
    await survey.getByRole("button", { name: "Continue to cancellation" }).click();
    await expect(survey).toBeHidden({ timeout: 15_000 });
  }

  // Step 3: back to campable — webhook → DB → UI loop validation.
  // This is the assertion that matters: it covers our own
  // Stripe → webhook → DB → BillingProvider chain rather than Stripe's copy,
  // which is why there's no assertion on the Portal's confirmation wording.
  // The webhook round trip can take 30-60s.
  await page.goto("/");
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Billing" }).click();
  await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 60_000 });
});
