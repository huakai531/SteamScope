import { defineConfig } from "@playwright/test";
import { randomUUID } from "node:crypto";

if (process.env.SOCIAL_ENVIRONMENT !== "test")
  throw new Error("Auth browser tests require the isolated test environment");

export default defineConfig({
  testDir: "./tests/auth-e2e",
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:3200",
    trace: "off",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "uv run --frozen --project ../backend python ../backend/tests/browser_server.py",
      url: "http://127.0.0.1:8200/health/live",
      timeout: 60000,
      reuseExistingServer: false,
      env: {
        SOCIAL_BROWSER_ORIGIN: "http://127.0.0.1:3200",
        SOCIAL_COOKIE_SECURE: "false",
        SOCIAL_AUTH_RATE_LIMIT: "1000",
        SOCIAL_SENSITIVE_RATE_LIMIT: "1000",
        SOCIAL_BROWSER_STEAM_SYNC: "1",
        SOCIAL_REDIS_NAMESPACE: "browser_" + randomUUID().replaceAll("-", ""),
      },
      gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
    },
    {
      command:
        "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3200",
      url: "http://127.0.0.1:3200",
      timeout: 60000,
      reuseExistingServer: false,
      env: {
        INTERNAL_API_URL: "http://127.0.0.1:8200",
        BROWSER_ORIGIN: "http://127.0.0.1:3200",
      },
      gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
    },
  ],
});
