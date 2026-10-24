import { expect, test } from "@playwright/test";
import { identity, login, steam } from "./helpers";
import { saveVisual } from "./visual-capture";

test("privacy popup preserves values and keyboard navigation; connection tabs remain accessible", async ({
  page,
  context,
}) => {
  await steam(context, identity());
  await login(page);
  const before = await (
    await page.request.get("/api/v1/me/steam/sync-status")
  ).json();
  await page.goto("/account/privacy");
  const control = page.getByRole("combobox", {
    name: "Library visibility",
    exact: true,
  });
  await expect(control).toHaveText("Only me");
  await control.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(control).toHaveText("Public (signed-in players)");
  await expect(control).toBeFocused();
  await page.getByRole("button", { name: "Save privacy preferences" }).click();
  await expect(page.getByText("Privacy preferences saved.")).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/me/privacy")).json()).library,
  ).toBe("public");
  await page.reload();
  await expect(control).toHaveText("Public (signed-in players)");
  await control.click();
  await page
    .getByRole("option", {
      name: "Accepted SteamScope connections",
      exact: true,
    })
    .click();
  await expect(control).toHaveText("Accepted SteamScope connections");
  await page.getByRole("button", { name: "Save privacy preferences" }).click();
  await expect(page.getByText("Privacy preferences saved.")).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/me/privacy")).json()).library,
  ).toBe("connections");
  await page.setViewportSize({ width: 390, height: 844 });
  await control.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("listbox")).toBeVisible();
  // Wait for the real opening transition before taking visual evidence.
  await expect(page.locator(".bui-select-content")).toHaveCSS("opacity", "1");
  const popup = await page.locator(".bui-select-content").boundingBox();
  expect(popup!.x).toBeGreaterThanOrEqual(0);
  expect(popup!.x + popup!.width).toBeLessThanOrEqual(390);
  expect(popup!.y + popup!.height).toBeLessThanOrEqual(844);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  if (process.env.BUI_CAPTURE_DIR)
    await saveVisual(
      page,
      process.env.BUI_CAPTURE_DIR,
      "privacy-select-mobile",
    );
  await page.keyboard.press("Escape");
  await expect(control).toBeFocused();
  await page.goto("/connections");
  const tabs = page.getByRole("radiogroup", { name: "Connection sections" });
  await tabs.getByRole("radio", { name: "Connections", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    tabs.getByRole("radio", { name: "Requests", exact: true }),
  ).toBeChecked();
  await expect(page.getByText("No incoming requests.")).toBeVisible();
  await page.keyboard.press("End");
  await expect(
    tabs.getByRole("radio", { name: "Blocked", exact: true }),
  ).toBeChecked();
  await expect(page.getByText("You have not blocked anyone.")).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/me/steam/sync-status")).json())
      .latest_job,
  ).toEqual(before.latest_job);
});
