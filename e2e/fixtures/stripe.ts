import { FrameLocator, Page, expect } from "@playwright/test";

/**
 * Stripe Checkout helper — for the modern hosted Checkout page
 * at checkout.stripe.com.
 *
 * Stripe serves two Checkout variants, chosen per session. `payWithCard`
 * detects which one loaded and drives it; neither is going away on a date we
 * know, so both paths stay.
 *
 * Top-page variant — DOM verified via Chrome DevTools MCP against a real
 * staging session (2026-05-30):
 *
 *   - Payment-method block is an accordion: Card, Cash App Pay, Klarna,
 *     Bank. Click the Card item to expand the card form inline.
 *   - Target it by `data-testid="card-accordion-item"`, not by role. Until
 *     late Sep 2026 the item held an `<input type=radio>` named "Card";
 *     Stripe then swapped it for an aria-hidden decorative span, so
 *     `getByRole("radio", { name: "Card" })` matched nothing and every
 *     Checkout flow timed out (nightly red from 2026-09-30). The test id
 *     survived that change; the role did not.
 *   - Fields render in the page accessibility tree, accessible by label.
 *   - All required for US: card number, expiration, CVC, cardholder
 *     name, ZIP, phone number.
 *   - Submit button text: "Subscribe".
 *
 * Iframe variant ("guacamole") — first served 2026-11-11 and red in the
 * nightly from then (#221). DOM verified by aria snapshot against staging,
 * 2026-11-13:
 *
 *   - `<html data-checkout-variant="guacamole">`. The top page holds only the
 *     header, price and one Stripe iframe. Everything else (Link button and
 *     email, the payment-method accordion, every card and billing field and
 *     the submit button) is inside that iframe.
 *   - The iframe's title is "Secure embedded form frame" (one earlier trace
 *     showed "Secure payment input frame"); its name is a generated
 *     `__privateStripeFrameNNNN`, so scope by title. Other Stripe iframes on
 *     the page carry other titles ("Bank search results") or none.
 *   - Card item: `[role=button][data-value="card"]`, collapsed
 *     (`aria-expanded="false"`) on load. Siblings: Cash App Pay, Klarna, Bank.
 *   - Expanded labels differ from the top-page variant: "Card number",
 *     "Expiration (MM/YY)", "Security code", "Name on card", "ZIP code"
 *     (Country select defaults to United States).
 *   - A "Save my information for faster checkout" (Link) checkbox is checked
 *     by default and adds a "Mobile number" field. We uncheck it so the
 *     flow doesn't create a Link account.
 *   - Submit: `data-testid="payment-form-submit-button"`, text "Subscribe".
 */

const DEFAULTS = {
  cardNumber: "4242424242424242",
  cardExpiry: "12 / 30",
  cardCvc: "123",
  cardholderName: "E2E Smoke",
  zip: "98101",
  phone: "2065551234",
};

type CardValues = typeof DEFAULTS;

const EMBEDDED_FORM_FRAME =
  'iframe[title="Secure embedded form frame"], iframe[title="Secure payment input frame"]';

export async function payWithCard(
  page: Page,
  overrides: Partial<CardValues> = {},
): Promise<void> {
  const values = { ...DEFAULTS, ...overrides };

  const topPageCard = page.getByTestId("card-accordion-item");
  // .first(): only the iframe variant has a frame with these titles today,
  // but a strict-mode error here would sink the top-page path too.
  const form = page.frameLocator(EMBEDDED_FORM_FRAME).first();
  const frameCard = form.locator('[role=button][data-value="card"]');

  // Whichever Card item renders first tells us the variant. Promise.any, not
  // race: the loser's waitFor eventually times out, and that must not fail
  // the run once the winner has resolved.
  const variant = await Promise.any([
    topPageCard.waitFor({ timeout: 30_000 }).then(() => "top-page" as const),
    frameCard.waitFor({ timeout: 30_000 }).then(() => "iframe" as const),
  ]);
  // Logged so CI output shows which variant each run hit.
  console.log(`Stripe Checkout variant: ${variant}`);

  if (variant === "iframe") {
    await payInEmbeddedForm(form, values);
  } else {
    await payOnTopPage(page, values);
  }
}

async function payOnTopPage(page: Page, values: CardValues): Promise<void> {
  // Expand the Card item. Not the "Pay with card" button — that only becomes
  // the action button after the form is filled.
  await page.getByTestId("card-accordion-item").click();

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

async function payInEmbeddedForm(form: FrameLocator, values: CardValues): Promise<void> {
  const card = form.locator('[role=button][data-value="card"]');
  // Clicking an already-open accordion item may collapse it.
  if ((await card.getAttribute("aria-expanded")) !== "true") {
    await card.click();
  }
  await expect(card).toHaveAttribute("aria-expanded", "true");

  await form.getByRole("textbox", { name: "Card number" }).fill(values.cardNumber);
  await form.getByRole("textbox", { name: /^Expiration/ }).fill(values.cardExpiry);
  await form.getByRole("textbox", { name: "Security code" }).fill(values.cardCvc);
  await form.getByRole("textbox", { name: "Name on card" }).fill(values.cardholderName);
  await form.getByRole("textbox", { name: /^ZIP/ }).fill(values.zip);

  const saveInfo = form.getByRole("checkbox", { name: /Save my information/ });
  if (await saveInfo.isVisible()) {
    await saveInfo.setChecked(false);
    // Wait for the Link phone field to collapse. An earlier version saw it
    // still visible mid-collapse and typed a phone into it; Subscribe then
    // did nothing (no confirm request) and the run timed out (2026-11-13).
    await expect(form.getByRole("textbox", { name: "Mobile number" })).toBeHidden();
  }

  await form.getByTestId("payment-form-submit-button").click();
}

/** Wait until the webhook → DB → UI loop has rendered the Pro badge in the header. */
export async function waitForProBadge(page: Page): Promise<void> {
  await expect(page.locator(".pro-badge").first()).toBeVisible({ timeout: 60_000 });
}
