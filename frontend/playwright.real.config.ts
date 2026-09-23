import { defineConfig, devices } from "@playwright/test";

const apiUrl = process.env.DOCUMIND_REAL_API;
if (!apiUrl) {
  throw new Error(
    "DOCUMIND_REAL_API is required. Start the isolated API and run npm run test:e2e:real.",
  );
}

const frontendUrl = "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./e2e-real",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: {
    timeout: 30_000,
  },
  reporter: [["list"]],
  use: {
    baseURL: frontendUrl,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiUrl,
        VITE_QUERY_REFRESH_INTERVAL_MS: "500",
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: ["--no-proxy-server"],
        },
      },
    },
  ],
});
