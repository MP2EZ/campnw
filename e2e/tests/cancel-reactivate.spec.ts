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

  // Portal flow: "Cancel subscription" opens a confirm page, which opens a
  // reason-survey modal; "Continue to cancellation" dismisses it, then the
  // confirm page's "Cancel subscription" finalises.
  //
  // The survey modal leaves the confirm button visible but pointer-blocked
  // under Stripe's overlay, so dismiss it first. That also rules out
  // .first()/.last() past the entry click: they re-bind to the unclickable node.
  //
  // Portal steps are best-effort and never assert on Stripe's copy, which
  // changes without notice. The "Pro until" check below is the real assertion:
  // skipping a step can give a false failure, never a false pass.
  // Register before the first click so the request can't be missed.
  const cancelSubmitted = page.waitForResponse(
    (r) => r.request().method() === "POST" && /\/subscriptions\/[^/]+\/cancel\b/.test(r.url()),
    { timeout: 30_000 },
  );

  await page.getByText("Cancel subscription", { exact: true }).first().click();

  const survey = page.getByRole("alertdialog", { name: /cancel your subscription/i });
  if (await appears(survey)) {
    await survey.getByRole("button", { name: "Continue to cancellation" }).click();
    await expect(survey).toBeHidden({ timeout: 15_000 });
  }

  const confirmCancel = page.getByRole("button", { name: "Cancel subscription" });
  if (await appears(confirmCancel)) {
    await confirmCancel.click();
  }

  // Wait on our own request, not networkidle: goto() below would abort the
  // cancel POST in flight. If it never fires, the cancel didn't happen.
  await cancelSubmitted;

  // Step 3: back to campable, which checks our webhook -> DB -> UI chain.
  // Reload inside the retry because BillingProvider fetches status once on
  // mount and never polls; the webhook can take 30-60s.
  await expect(async () => {
    await page.goto("/");
    await page.locator(".user-menu-trigger").click();
    await page.getByRole("button", { name: "Billing" }).click();
    await expect(page.getByText(/Pro until/i)).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 60_000, intervals: [2_000, 5_000] });
});
