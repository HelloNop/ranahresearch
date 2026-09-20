import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: { baseURL: "http://127.0.0.1:3100", headless: true },
  webServer: { command: "npm run dev -- --port 3100", url: "http://127.0.0.1:3100", reuseExistingServer: !process.env.CI },
});
