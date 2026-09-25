// Page tests: Chromium against the built UI (ui/dist) served by the API on the
// default world. `npm run build` first; `npm run e2e` starts the API itself.
// SDF_E2E_CHROMIUM points at an installed Chromium instead of Playwright's own.
import { defineConfig, devices } from "@playwright/test";

const PORT = 8123;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1, // one API server for every test: a slow study in one test would time another out
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: process.env.SDF_E2E_CHROMIUM ? { executablePath: process.env.SDF_E2E_CHROMIUM } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run uvicorn sdf.api.app:app --host 127.0.0.1 --port ${PORT}`,
    cwd: "..",
    env: { SDF_UI_DIR: "ui/dist" },
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
