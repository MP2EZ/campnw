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

/**
 * Sign up a fresh user. Email is timestamped per run so concurrent runs
 * don't collide. Returns the email used so tests can log it.
 */
export async function signupFresh(
  page: Page,
  opts: { displayName?: string; password?: string } = {},
): Promise<string> {
  const password = opts.password ?? "PlaywrightE2E2026!";
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const email = `e2e-fresh-${stamp}@maestro.test`;

  await page.goto("/");
  await openModal(page);
  await page.getByRole("button", { name: "Create one" }).click();
  if (opts.displayName) {
    await page.getByTestId("display-name-input").fill(opts.displayName);
  }
  await page.getByTestId("email-input").fill(email);
  await page.getByTestId("password-input").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  // Wait for the modal to close (onClose() fires inside AuthModal's
  // handleSubmit success path). The dialog locator is unambiguous;
  // `getByRole("button", { name: "Sign in" })` matches both the header
  // trigger AND the auth-switch-btn during signup mode, which trips
  // Playwright's strict-mode locator uniqueness check.
  await expect(page.getByRole("dialog")).toBeHidden({ timeout: 30_000 });
  return email;
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

  await expect(page.getByRole("dialog")).toBeHidden({ timeout: 30_000 });
}

/**
 * Dismiss the 2-step "Welcome to campable" onboarding modal new users see
 * before they can navigate to /pricing. No-op if the modal isn't visible.
 */
export async function skipOnboarding(page: Page): Promise<void> {
  const onboard = page.getByText("Welcome to campable");
  for (let step = 0; step < 2; step += 1) {
    const visible = await onboard.isVisible({ timeout: 2_000 }).catch(() => false);
    if (!visible) return;
    await page.getByRole("button", { name: "Skip" }).click();
  }
}
