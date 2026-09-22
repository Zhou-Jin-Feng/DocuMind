import { defineConfig, devices } from "@playwright/test";

process.env.DOCUMIND_STREAMING_REPORT_PATH ??=
  "../artifacts/frontend-3.1.0/fe03/streaming-after-r2.json";
process.env.DOCUMIND_STREAMING_WRITE_MODE ??= "replace";

const frontendUrl = "http://127.0.0.1:4273";
const apiUrl = "http://127.0.0.1:4274";

export default defineConfig({
  testDir: "./benchmarks",
  testMatch: "fe01-streaming.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  outputDir: "../artifacts/frontend-3.1.0/fe03/playwright-results",
  reporter: [["list"]],
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "node benchmarks/fe01-mock-api.mjs",
      url: `${apiUrl}/__fe01/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command:
        "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4273 --strictPort --outDir ../artifacts/frontend-3.1.0/fe03/profile-dist",
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: "chromium-production-fe03",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
