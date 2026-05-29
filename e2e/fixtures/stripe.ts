import { Page, expect } from "@playwright/test";

/**
 * Stripe Checkout iframe helper.
 *
 * The DOM shape (verified via Phase 0 spike against campable.co):
 *   - Payment-method tabs at top: Apple Pay / Link / Amazon Pay buttons
 *   - Radio options below tabs: Card / Cash App Pay / Klarna / Bank
 *   - Must click "Card" radio to expand card form inline
 *   - Card form fields render in a cross-origin iframe (Playwright
 *     handles these natively via frameLocator)
 *   - Submit button text: "Subscribe"
 *
 * Default values are the Stripe test mode "always succeed" card.
 */

const STRIPE_FRAME_SELECTOR = 'iframe[name^="__privateStripeFrame"]';

const DEFAULTS = {
  cardNumber: "4242424242424242",
  cardExpiry: "12 / 30",
  cardCvc: "123",
};

export async function payWithCard(
  page: Page,
  overrides: Partial<typeof DEFAULTS> = {},
): Promise<void> {
  const values = { ...DEFAULTS, ...overrides };

  // Select Card from the payment-method radios
  await page.getByText("Card", { exact: true }).first().click();

  const frame = page.frameLocator(STRIPE_FRAME_SELECTOR).first();
  await frame.locator('input[name="cardNumber"]').fill(values.cardNumber);
  await frame.locator('input[name="cardExpiry"]').fill(values.cardExpiry);
  await frame.locator('input[name="cardCvc"]').fill(values.cardCvc);

  await page.getByRole("button", { name: "Subscribe" }).click();
}

/** Wait until the webhook → DB → UI loop has rendered the Pro badge in the header. */
export async function waitForProBadge(page: Page): Promise<void> {
  await expect(page.locator(".pro-badge").first()).toBeVisible({ timeout: 60_000 });
}
