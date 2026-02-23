import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    extraHTTPHeaders: {
      Accept: "application/json",
    },
  },
  /* Start Next.js dev server before tests */
  webServer: {
    command: "npm run dev",
    port: 3000,
    timeout: 60_000,
    reuseExistingServer: true,
  },
});
