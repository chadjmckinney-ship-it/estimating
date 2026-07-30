import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests for the static SPA.
 *
 * Points at the normal dev server on 8001 and reuses it if already running, so
 * this exercises exactly what the browser gets — no bundling, no test build.
 *
 * The suite is READ-ONLY against the live `estimating` database: it loads pages
 * and opens dialogs, but never clicks Save, Recalculate or Delete. Keep it that
 * way, or a test run will quietly edit real bids.
 */
const PORT = process.env.ESTIMATING_PORT || "8001";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      "../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port " + PORT,
    cwd: "backend",
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
