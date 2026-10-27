import { defineConfig, devices } from "@playwright/test";

const API_PORT = process.env.E2E_API_PORT ?? "8100";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "3100";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/start-backend.mjs",
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      env: { E2E_API_PORT: API_PORT },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // Production build so the test exercises the same /api rewrite proxy as deployment.
      command: `npm run build && npx next start --hostname 127.0.0.1 --port ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}/login`,
      env: { BACKEND_URL: `http://127.0.0.1:${API_PORT}`, NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
