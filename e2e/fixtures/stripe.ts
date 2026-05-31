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

  // Card form expands inline. Scope to role=textbox so the label match
  // doesn't accidentally hit info icons or country-code comboboxes that
  // share label substrings (e.g., a "CVC" info image, a "Phone number
  // country code" combobox).
  await page.getByRole("textbox", { name: "Card number" }).fill(values.cardNumber);
  await page.getByRole("textbox", { name: "Expiration" }).fill(values.cardExpiry);
  await page.getByRole("textbox", { name: "CVC" }).fill(values.cardCvc);
  await page.getByRole("textbox", { name: "Cardholder name" }).fill(values.cardholderName);
  await page.getByRole("textbox", { name: "ZIP" }).fill(values.zip);
  await page.getByRole("textbox", { name: "Phone number", exact: true }).fill(values.phone);

  await page.getByRole("button", { name: "Subscribe" }).click();
}

/** Wait until the webhook → DB → UI loop has rendered the Pro badge in the header. */
export async function waitForProBadge(page: Page): Promise<void> {
  await expect(page.locator(".pro-badge").first()).toBeVisible({ timeout: 60_000 });
}
