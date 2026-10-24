import { expect, test } from "@playwright/test";
import { identity, steam, login } from "./helpers";

test("controlled login, profile/privacy persistence, reload, logout and no protected flash", async ({
  page,
  context,
}) => {
  const id = identity();
  await steam(context, id);
  await login(page);
  await expect(page.getByText(id, { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/account-desktop.png",
    fullPage: true,
  });
  const cookies = await context.cookies();
  expect(
    cookies.find((cookie) => cookie.name === "steamscope_session")?.httpOnly,
  ).toBe(true);
  expect(cookies.some((cookie) => cookie.name.startsWith("ss_login_"))).toBe(
    false,
  );
  await page.getByRole("link", { name: "Profile", exact: true }).click();
  await page
    .getByLabel("Display name", { exact: true })
    .fill("Browser chosen name");
  await page
    .getByLabel("Biography")
    .fill("Plain text <script> is not executed.");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved.");
  await page.reload();
  await expect(page.getByLabel("Display name", { exact: true })).toHaveValue(
    "Browser chosen name",
  );
  await page.getByRole("link", { name: "Privacy", exact: true }).click();
  await expect(page.getByLabel("Profile visibility")).toHaveText("Only me");
  await page.getByLabel("Allow discovery and search participation").check();
  await page.getByRole("button", { name: "Save privacy preferences" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Privacy preferences saved.",
  );
  await page.reload();
  await expect(
    page.getByLabel("Allow discovery and search participation"),
  ).toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/privacy-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("You are logged out.");
  await page.addInitScript(() => {
    (window as unknown as { leaked: boolean }).leaked = false;
    new MutationObserver(() => {
      if (document.body?.textContent?.includes("Browser chosen name"))
        (window as unknown as { leaked: boolean }).leaked = true;
    }).observe(document, { childList: true, subtree: true });
  });
  await page.goto("/account");
  await expect(
    page.getByRole("heading", { name: "Sign in to your account" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { leaked: boolean }).leaked,
    ),
  ).toBe(false);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
});

test("two browser contexts remain isolated; owned session revocation and logout-all", async ({
  browser,
}) => {
  const first = await browser.newContext({ baseURL: "http://127.0.0.1:3200" }),
    second = await browser.newContext({ baseURL: "http://127.0.0.1:3200" });
  try {
    const id1 = identity(),
      id2 = identity();
    await steam(first, id1);
    await steam(second, id2);
    const one = await first.newPage(),
      two = await second.newPage();
    await login(one);
    await login(two);
    await expect(one.getByText(id2, { exact: true })).toHaveCount(0);
    await expect(two.getByText(id1, { exact: true })).toHaveCount(0);
    await one.getByRole("link", { name: "Sessions", exact: true }).click();
    await one.getByRole("button", { name: "Revoke this session" }).click();
    await expect(one.getByRole("status")).toHaveText("You are logged out.");
    await two.reload();
    await expect(two.getByText(id2, { exact: true })).toBeVisible();
    await two.getByRole("link", { name: "Sessions", exact: true }).click();
    await two.getByRole("button", { name: "Log out all sessions" }).click();
    await expect(two.getByRole("dialog")).toBeVisible();
    await two.getByRole("button", { name: "Confirm logout all" }).click();
    await expect(two.getByRole("status")).toHaveText(
      "All your sessions have been revoked.",
    );
  } finally {
    await first.close();
    await second.close();
  }
});

test("account deletion confirmation and safe cancellation", async ({
  page,
  context,
}) => {
  await steam(context, identity());
  await login(page);
  await page.getByRole("link", { name: "Delete account", exact: true }).click();
  await page.getByRole("button", { name: "Delete my account" }).click();
  await expect(
    page.getByRole("button", { name: "Permanently delete account" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Delete my account" }).click();
  await page.getByLabel("Confirmation", { exact: true }).fill("DELETE");
  await page
    .getByRole("button", { name: "Permanently delete account" })
    .click();
  await expect(page.getByRole("status")).toHaveText(
    "Your SteamScope account has been deleted.",
  );
  await page.goto("/account");
  await expect(
    page.getByRole("heading", { name: "Sign in to your account" }),
  ).toBeVisible();
});

test("Steam cancellation is shown without authentication or assertion parameters", async ({
  page,
  context,
}) => {
  await steam(context, identity(), true);
  await page.goto("/");
  await page.getByRole("link", { name: "Continue with Steam" }).click();
  await expect(page.getByRole("alert")).toContainText("cancelled");
  expect(page.url()).not.toContain("openid.");
  expect(
    (await context.cookies()).some(
      (cookie) => cookie.name === "steamscope_session",
    ),
  ).toBe(false);
});
