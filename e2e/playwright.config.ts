import { defineConfig, devices } from "@playwright/test";

/**
 * Campable E2E config.
 *
 * E2E_BASE_URL targets:
 *   - local iteration: http://localhost:5173 (Vite dev) or https://campable.co (prod)
 *   - CI per-PR: https://campnw-pr-<n>.fly.dev (Fly preview deployment)
 *   - CI nightly: https://campnw-staging.fly.dev
 */
const baseURL = process.env.E2E_BASE_URL || "https://campable.co";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["html"], ["github"], ["list"]]
    : [["html"], ["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
