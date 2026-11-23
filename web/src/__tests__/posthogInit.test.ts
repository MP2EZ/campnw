import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test, vi } from "vitest";
import { KNOWN_BASE_KEYS } from "../lib/bases";

// SEC-16: custom origin addresses and free-text queries in the page URL must
// not reach PostHog. Runs the real public/posthog-init.js against a stub.
function loadConfig() {
  const init = vi.fn();
  (window as unknown as { posthog: unknown }).posthog = { __SV: 1, init };
  const code = readFileSync(resolve(__dirname, "../../public/posthog-init.js"), "utf8");
  new Function(code)();
  return init.mock.calls[0][1] as {
    before_send: (e: Record<string, unknown>) => Record<string, unknown>;
  };
}

describe("posthog-init before_send", () => {
  const send = (props: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
    loadConfig().before_send({ event: "$pageview", properties: props, ...extra });

  test("redacts a custom from address and the q text", () => {
    const out = send({
      $current_url: "https://campable.co/?from_location=12+Elm+St%2C+Olympia&q=near+my+house&state=WA",
    });
    const url = new URL((out.properties as Record<string, string>).$current_url);
    expect(url.searchParams.get("from_location")).toBe("custom");
    expect(url.searchParams.get("q")).toBe("redacted");
    expect(url.searchParams.get("state")).toBe("WA");
  });

  test("keeps a known base", () => {
    const out = send({ $referrer: "https://campable.co/?from_location=seattle" });
    expect((out.properties as Record<string, string>).$referrer).toContain("from_location=seattle");
  });

  test("scrubs person initial URLs too", () => {
    const out = send({}, { $set_once: { $initial_current_url: "https://campable.co/?from=1+Main+St" } });
    expect((out.$set_once as Record<string, string>).$initial_current_url).toContain("from=custom");
  });

  test("leaves non-URL values and missing properties alone", () => {
    expect(send({ $current_url: "not a url" }).properties).toEqual({ $current_url: "not a url" });
    expect(loadConfig().before_send({ event: "x" })).toEqual({ event: "x" });
  });

  test("its base list matches the app's", () => {
    const code = readFileSync(resolve(__dirname, "../../public/posthog-init.js"), "utf8");
    const list = code.match(/KNOWN_BASES = \[([^\]]*)\]/)![1];
    expect(list.match(/[a-z]+/g)!.sort()).toEqual([...KNOWN_BASE_KEYS].sort());
  });
});
