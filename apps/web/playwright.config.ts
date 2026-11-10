import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "../..");
const PY = process.env.PYTHON || (process.platform === "win32" ? `"${path.join(ROOT, ".venv", "Scripts", "python.exe")}"` : "python");
const SERVER = `"${path.join(ROOT, "tools", "e2e_server.py")}"`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 360_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  globalSetup: "./tests/e2e/global-setup.ts",
  use: { baseURL: "http://127.0.0.1:8010", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile/ },
  ],
  webServer: [
    { command: `${PY} ${SERVER} 8010`, url: "http://127.0.0.1:8010/health", timeout: 240_000, reuseExistingServer: !process.env.CI },
    { command: `${PY} ${SERVER} 8011 --degraded`, url: "http://127.0.0.1:8011/health", timeout: 240_000, reuseExistingServer: !process.env.CI },
  ],
});
