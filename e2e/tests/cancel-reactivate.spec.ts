import { test, expect, type Locator } from "@playwright/test";
import { signupFresh, skipOnboarding } from "../fixtures/auth";
import { payWithCard, waitForProBadge } from "../fixtures/stripe";

/** Resolves true if the locator becomes visible in time, false if it never does. */
async function appears(locator: Locator, timeout = 10_000): Promise<boolean> {
  return locator.waitFor({ state: "visible", timeout }).then(
    () => true,
    () => false,
  );
}

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

  // Stripe Portal cancel flow, as observed 2026-08:
  //   portal home "Cancel subscription"
  //     -> "Confirm cancellation" page, which opens a "Cancel your
  //        subscription" reason-survey modal on top of itself
  //     -> modal "Continue to cancellation" dismisses the survey
  //     -> confirm page "Cancel subscription" finalises
  //
  // Order matters: the survey modal leaves the confirm button visible and
  // enabled but pointer-blocked underneath Stripe's overlay layer, so it must
  // be dismissed first. That also rules out ordinal locators past the entry
  // click — .first()/.last() silently re-bind to the unclickable node.
  //
  // Both Portal-side steps are best-effort. Stripe toggles the survey via a
  // Portal setting and has reshaped this flow before, so a missing step
  // shouldn't fail the run. The authoritative assertion is the "Pro until"
  // check below: it can't pass unless cancellation really propagated, so
  // skipping a step here can produce a false failure but never a false pass.
  await page.getByText("Cancel subscription", { exact: true }).first().click();
  await expect(page.getByText("Confirm cancellation")).toBeVisible({ timeout: 15_000 });

  const survey = page.getByRole("alertdialog", { name: /cancel your subscription/i });
  if (await appears(survey)) {
    // The reason select is optional — "Continue to cancellation" is enabled
    // without choosing one.
    await survey.getByRole("button", { name: "Continue to cancellation" }).click();
    await expect(survey).toBeHidden({ timeout: 15_000 });
  }

  const confirmCancel = page.getByRole("button", { name: "Cancel subscription" });
  if (await appears(confirmCancel)) {
    await confirmCancel.click();
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
