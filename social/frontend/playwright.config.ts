import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: "http://127.0.0.1:3100" },
  webServer: {
    command: "npm run start",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
  },
});
