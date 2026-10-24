import { expect, test } from "@playwright/test";
import { identity, steam, login } from "./helpers";

test("owner sync uses real pipeline, saved pagination, confirmation and no cross-user disclosure", async ({
  browser,
}) => {
  const first = await browser.newContext(),
    second = await browser.newContext();
  try {
    await steam(first, identity());
    await steam(second, identity());
    const one = await first.newPage(),
      two = await second.newPage();
    await login(one);
    await login(two);
    await one.getByRole("link", { name: "My Steam Data" }).click();
    await two.getByRole("link", { name: "My Steam Data" }).click();
    await expect(
      one.getByText("Never synchronized", { exact: true }).first(),
    ).toBeVisible();
    await one.getByRole("button", { name: "Sync my Steam data" }).click();
    await expect(one.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 15000,
    });
    await expect(
      one.getByText("Synthetic Steam persona", { exact: true }),
    ).toBeVisible();
    await expect(
      one.locator("strong").filter({ hasText: /^Synthetic Game 25$/ }),
    ).toBeVisible();
    await expect(
      two.getByText("Synthetic Steam persona", { exact: true }),
    ).toHaveCount(0);
    await expect(
      two.getByText("Never synchronized", { exact: true }).first(),
    ).toBeVisible();
    await one.getByRole("button", { name: "Next page" }).click();
    await expect(
      one.locator("strong").filter({ hasText: /^Synthetic Game 27$/ }),
    ).toBeVisible();
    await one.reload();
    await expect(
      one.locator("strong").filter({ hasText: /^Synthetic Game 25$/ }),
    ).toBeVisible();
    await expect(
      one.getByRole("button", { name: "Clear imported Steam data" }),
    ).toBeDisabled();
    await one
      .getByLabel("Type CLEAR STEAM DATA to confirm")
      .fill("CLEAR STEAM DATA");
    await one
      .getByRole("button", { name: "Clear imported Steam data" })
      .click();
    await expect(one.getByText(/Imported Steam data cleared/)).toBeVisible();
    await expect(
      one.getByText("Synthetic Steam persona", { exact: true }),
    ).toHaveCount(0);
    await one.reload();
    await expect(
      one.getByText("Never synchronized", { exact: true }).first(),
    ).toBeVisible();
    await one.setViewportSize({ width: 390, height: 844 });
    await one.screenshot({
      path: "test-results/steam-data-mobile.png",
      fullPage: true,
    });
    expect(
      await one.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await one.getByRole("button", { name: "Log out", exact: true }).click();
    await expect(one).toHaveURL(/login/);
    await one.goto("/account/steam");
    await expect(
      one.getByRole("heading", { name: "Sign in to your account" }),
    ).toBeVisible();
    await expect(
      one.getByText("Synthetic Game 1", { exact: true }),
    ).toHaveCount(0);
  } finally {
    await first.close();
    await second.close();
  }
});
