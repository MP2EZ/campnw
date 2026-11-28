import { test, expect, type Page } from "@playwright/test";
import { signupFresh, skipOnboarding } from "../fixtures/auth";
import { payWithCard, waitForProBadge } from "../fixtures/stripe";

/**
 * Flow 6 — Delete a Pro account (DEBUG-13).
 *
 * signup → upgrade → Delete account → signed out, and the old sign-in token
 * can no longer use or recreate the account.
 *
 * The server cancels the Stripe subscription before deleting; this flow
 * asserts the delete succeeded (it returns 502 if the cancel fails). Checking
 * the subscription's status in Stripe needs the staging Stripe key, which CI
 * doesn't have; see the PR for the one-off check against Stripe test mode.
 */

/** The Supabase access token the app is signed in with. */
async function accessToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("sb-") && key.endsWith("-auth-token")) {
        return JSON.parse(localStorage.getItem(key) || "{}").access_token ?? "";
      }
    }
    return "";
  });
  expect(token, "Supabase session in localStorage").not.toBe("");
  return token;
}

test("Pro user can delete their account; the old token is refused", async ({ page }) => {
  test.setTimeout(180_000);

  await signupFresh(page, { displayName: "E2E Delete" });
  await page.goto("/pricing");
  await skipOnboarding(page);
  await page.getByRole("button", { name: "Upgrade to Pro" }).click({ force: true });
  await expect(page).toHaveURL(/checkout\.stripe\.com/, { timeout: 30_000 });
  await payWithCard(page);
  await waitForProBadge(page);

  const token = await accessToken(page);
  const me = await page.request.get("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(me.status()).toBe(200);
  const userId = (await me.json()).user.id;
  console.log(`Deleting user ${userId}`);

  const deleted = page.waitForResponse(
    (r) => r.request().method() === "DELETE" && r.url().endsWith("/api/auth/me"),
  );
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("button", { name: "Delete account" }).click();
  await page.locator(".user-menu-confirm").getByRole("button", { name: "Delete" }).click();
  expect((await deleted).status()).toBe(200);

  // Signed out in the UI.
  await expect(page.getByRole("button", { name: "Sign in" }).first()).toBeVisible({
    timeout: 15_000,
  });

  // The token is still unexpired, but it must not bring the account back.
  const after = await page.request.get("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(after.status()).toBe(401);
});
