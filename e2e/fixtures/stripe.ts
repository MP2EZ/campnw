import { Page, expect } from "@playwright/test";

/**
 * Stripe Checkout helper — for the modern hosted Checkout page
 * at checkout.stripe.com.
 *
 * DOM verified via Chrome DevTools MCP against a real staging session
 * (2026-05-30). The flow:
 *
 *   - Payment-method block has radio options: Card, Cash App Pay,
 *     Klarna, Bank. The "Card" element has role=radio (NOT a button).
 *   - Click the Card radio to expand the card form inline.
 *   - Fields render in the page accessibility tree, accessible by label.
 *   - All required for US: card number, expiration, CVC, cardholder
 *     name, ZIP, phone number.
 *   - Submit button text: "Subscribe".
 */

const DEFAULTS = {
  cardNumber: "4242424242424242",
  cardExpiry: "12 / 30",
  cardCvc: "123",
  cardholderName: "E2E Smoke",
  zip: "98101",
  phone: "2065551234",
};

export async function payWithCard(
  page: Page,
  overrides: Partial<typeof DEFAULTS> = {},
): Promise<void> {
  const values = { ...DEFAULTS, ...overrides };

  // Select the Card radio (NOT the "Pay with card" button — that button
  // only becomes the action button AFTER the form is filled).
  await page.getByRole("radio", { name: "Card" }).click({ force: true });

  // Card form expands inline. Fields are reachable by their accessible
  // labels even though they render inside Stripe Elements iframes —
  // the accessibility tree exposes them at page scope.
  await page.getByLabel("Card number").fill(values.cardNumber);
  await page.getByLabel("Expiration").fill(values.cardExpiry);
  await page.getByLabel("CVC").fill(values.cardCvc);
  await page.getByLabel("Cardholder name").fill(values.cardholderName);
  await page.getByLabel("ZIP").fill(values.zip);
  await page.getByLabel("Phone number").fill(values.phone);

  await page.getByRole("button", { name: "Subscribe" }).click();
}

/** Wait until the webhook → DB → UI loop has rendered the Pro badge in the header. */
export async function waitForProBadge(page: Page): Promise<void> {
  await expect(page.locator(".pro-badge").first()).toBeVisible({ timeout: 60_000 });
}
