import { Page, expect } from "@playwright/test";

/**
 * Stripe Checkout helper.
 *
 * The DOM shape (Phase 0 spike against campable.co, 2026-05-29):
 *   - Payment-method tabs at top: Apple Pay / Link / Amazon Pay
 *   - Radio options below tabs: Card / Cash App Pay / Klarna / Bank
 *   - Must click "Card" radio to expand card form inline
 *   - Submit button text: "Subscribe"
 *
 * Card form rendering: Stripe Checkout (hosted page at checkout.stripe.com)
 * historically rendered card fields directly in the page DOM. Modern
 * variants may move them into a nested iframe for PCI scope reduction.
 * The helper tries the direct DOM first and falls back to iframe scoping
 * if needed. First CI run will tell us which path is active; iterate
 * via the Playwright trace viewer if the fallback also fails.
 *
 * Default values are the Stripe test mode "always succeed" card.
 */

const DEFAULTS = {
  cardNumber: "4242424242424242",
  cardExpiry: "12 / 30",
  cardCvc: "123",
};

async function fillCardFields(
  scope: { locator: (sel: string) => ReturnType<Page["locator"]> },
  values: typeof DEFAULTS,
): Promise<void> {
  await scope.locator('input[name="cardNumber"]').fill(values.cardNumber);
  await scope.locator('input[name="cardExpiry"]').fill(values.cardExpiry);
  await scope.locator('input[name="cardCvc"]').fill(values.cardCvc);
}

export async function payWithCard(
  page: Page,
  overrides: Partial<typeof DEFAULTS> = {},
): Promise<void> {
  const values = { ...DEFAULTS, ...overrides };

  // Select Card from the payment-method radios. Scope to the radio's
  // accordion item — there's also "Card number" heading text below
  // that would collide with a loose "Card" match.
  await page.locator('[data-testid="payment-method-accordion-item-card"], [id*="card"][role="button"], button:has-text("Card")').first().click();

  // Try direct DOM first (Checkout historically renders card fields
  // in-page). If the inputs aren't on the top-level page, fall through
  // to the iframe scope.
  const directField = page.locator('input[name="cardNumber"]');
  const inIframe = (await directField.count()) === 0;
  if (inIframe) {
    const frame = page.frameLocator('iframe[src*="stripe"], iframe[name*="stripe"]').first();
    await fillCardFields(frame, values);
  } else {
    await fillCardFields(page, values);
  }

  await page.getByRole("button", { name: "Subscribe" }).click();
}

/** Wait until the webhook → DB → UI loop has rendered the Pro badge in the header. */
export async function waitForProBadge(page: Page): Promise<void> {
  await expect(page.locator(".pro-badge").first()).toBeVisible({ timeout: 60_000 });
}
