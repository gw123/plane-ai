import { defineConfig } from "@playwright/test";
import { readPlaneE2EConfig } from "./tests/e2e/support/plane-e2e";

const config = readPlaneE2EConfig();

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "tmp/playwright/report" }]],
  outputDir: "tmp/playwright/test-results",
  use: {
    baseURL: config.baseURL,
    storageState: config.storageStatePath ?? undefined,
    headless: config.headless,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});
