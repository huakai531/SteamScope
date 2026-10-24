import { expect, type BrowserContext, type Page } from "@playwright/test";
import { randomBytes, randomUUID } from "node:crypto";

export function identity() {
  return (
    76561197960265728n + BigInt("0x" + randomBytes(3).toString("hex"))
  ).toString();
}

export async function steam(
  context: BrowserContext,
  id: string,
  cancelled = false,
) {
  // Playwright routes only the first request in an HTTP redirect chain. Split
  // the navigation in this test harness so the provider request is intercepted.
  // The real start endpoint still creates state and its browser-binding cookie.
  await context.route("**/api/v1/auth/steam/login*", async (route) => {
    const response = await route.fetch({ maxRedirects: 0 });
    expect(response.status()).toBe(303);
    const location = response.headers()["location"];
    expect(new URL(location).origin).toBe("https://steamcommunity.com");
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/html",
        "Cache-Control": "no-store",
        "Set-Cookie": response.headers()["set-cookie"],
      },
      body: `<script>location.replace(${JSON.stringify(location)})</script>`,
    });
  });
  await context.route(
    "https://steamcommunity.com/openid/login**",
    async (route) => {
      const start = new URL(route.request().url());
      const callback = new URL(start.searchParams.get("openid.return_to")!);
      const values = cancelled
        ? { "openid.mode": "cancel" }
        : {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "id_res",
            "openid.op_endpoint": "https://steamcommunity.com/openid/login",
            "openid.claimed_id": "http://steamcommunity.com/openid/id/" + id,
            "openid.identity": "http://steamcommunity.com/openid/id/" + id,
            "openid.return_to": callback.toString(),
            "openid.response_nonce":
              new Date().toISOString().replace(/\.\d{3}Z$/, "Z") + randomUUID(),
            "openid.assoc_handle": "fixture-association",
            "openid.signed":
              "op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
            "openid.sig": Buffer.from(
              "controlled-signature-fixture!!",
            ).toString("base64"),
          };
      for (const [key, value] of Object.entries(values))
        callback.searchParams.set(key, value!);
      await route.fulfill({
        status: 302,
        headers: { Location: callback.toString() },
      });
    },
  );
}

export async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("link", { name: "Continue with Steam" }).click();
  await expect(page.getByRole("heading", { name: "New player" })).toBeVisible();
  expect(new URL(page.url()).search).toBe("");
}
