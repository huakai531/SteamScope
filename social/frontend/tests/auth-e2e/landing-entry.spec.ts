import { expect, test } from "@playwright/test";
import { identity, login, steam } from "./helpers";

test("landing entry preserves verified redirect login and opens the existing account when signed in", async ({
  page,
  context,
}) => {
  await steam(context, identity());
  await login(page);
  await page.goto("/");
  await expect(
    page.getByRole("navigation").getByRole("link", { name: "Open SteamScope" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Continue with Steam" }),
  ).toHaveCount(0);
  await expect(page.locator(".product-preview")).not.toContainText(
    "New player",
  );
  await page
    .locator(".landing-copy")
    .getByRole("link", { name: /Open SteamScope/ })
    .click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", { name: "New player" })).toBeVisible();
});
