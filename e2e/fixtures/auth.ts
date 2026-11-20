import { Page, expect } from "@playwright/test";

/**
 * Auth helpers for campable E2E flows.
 *
 * `data-testid` attributes on the form inputs are defined in
 * web/src/components/AuthModal.tsx (added as part of v1.41).
 */

const FIXTURE_PASSWORD = process.env.E2E_FIXTURE_PASSWORD || "";
const FIXTURE_PREFIX = process.env.E2E_FIXTURE_PREFIX || "e2e-fixture-";

/** Open the auth modal from the landing page Sign in button. */
async function openModal(page: Page) {
  await page.getByRole("button", { name: "Sign in" }).first().click();
  await expect(page.getByTestId("email-input")).toBeVisible();
}

const SUPABASE_URL = process.env.SUPABASE_URL || "";
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
const FRESH_PASSWORD = "PlaywrightE2E2026!";

/**
 * Create a brand-new, already-confirmed user and sign in as them.
 *
 * Sign-up through the UI ends at "check your email" once Supabase's
 * "Confirm email" is on, and a test can't click the link. The admin API
 * creates the user pre-confirmed; the app creates its own user row on the
 * first authenticated request, the same as after a real confirmation.
 * Email is timestamped per call so retries and concurrent runs don't collide.
 */
export async function signupFresh(
  page: Page,
  opts: { displayName?: string } = {},
): Promise<void> {
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for signupFresh");
  }
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const email = `e2e-fresh-${stamp}@maestro.test`;

  const resp = await fetch(`${SUPABASE_URL}/auth/v1/admin/users`, {
    method: "POST",
    headers: {
      apikey: SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password: FRESH_PASSWORD,
      email_confirm: true,
      user_metadata: { display_name: opts.displayName || "" },
    }),
  });
  if (!resp.ok) {
    throw new Error(`admin create user failed: ${resp.status} ${await resp.text()}`);
  }

  await page.goto("/");
  await openModal(page);
  await page.getByTestId("email-input").fill(email);
  await page.getByTestId("password-input").fill(FRESH_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).last().click();

  // Wait for the AUTH modal specifically to close. A new user's onboarding
  // "Welcome to campable" modal opens right after — also role=dialog — so an
  // unscoped dialog selector never sees an empty state. Match by name.
  await expect(
    page.getByRole("dialog", { name: /Sign in|Create account/ }),
  ).toBeHidden({ timeout: 30_000 });
  await skipOnboarding(page);
}

/** Log in as a pre-seeded fixture user (created by scripts/seed_e2e_fixtures.py). */
export async function loginAsFixture(
  page: Page,
  slug: "free-3watches" | "free-3planner" | "pro",
): Promise<void> {
  if (!FIXTURE_PASSWORD) {
    throw new Error("E2E_FIXTURE_PASSWORD env var is required for fixture login");
  }
  const email = `${FIXTURE_PREFIX}${slug}@maestro.test`;

  await page.goto("/");
  await openModal(page);
  await page.getByTestId("email-input").fill(email);
  await page.getByTestId("password-input").fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).last().click();

  await expect(
    page.getByRole("dialog", { name: /Sign in|Create account/ }),
  ).toBeHidden({ timeout: 30_000 });
  await skipOnboarding(page);
}

/**
 * Dismiss the 2-step "Welcome to campable" onboarding modal new users see
 * before they can navigate to /pricing. No-op if the modal isn't visible.
 */
export async function skipOnboarding(page: Page): Promise<void> {
  // Onboarding modal appears after /api/auth/me returns + BillingProvider
  // sync — can be 5-15s after auth modal closes, and can re-trigger
  // after navigation. This helper is safe to call multiple times.
  const onboard = page.getByText("Welcome to campable");
  for (let step = 0; step < 2; step += 1) {
    const visible = await onboard.isVisible({ timeout: 15_000 }).catch(() => false);
    if (!visible) return;
    await page.getByRole("button", { name: "Skip" }).click({ force: true });
    // Wait for the modal to actually go away before next iteration
    await onboard.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  }
}
