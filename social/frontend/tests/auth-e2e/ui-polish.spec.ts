import { expect, test, type Page } from "@playwright/test";
import { identity, login, steam } from "./helpers";
import { saveVisual } from "./visual-capture";

async function write(
  page: Page,
  path: string,
  data?: unknown,
  method = "POST",
) {
  const csrf = await (await page.request.get("/api/v1/auth/csrf")).json();
  const response = await page.request.fetch("/api/v1" + path, {
    method,
    data,
    headers: {
      Origin: "http://127.0.0.1:3200",
      "X-CSRF-Token": csrf.csrf_token,
    },
  });
  expect(response.ok()).toBeTruthy();
  return response;
}
async function prepare(page: Page, name: string) {
  await write(
    page,
    "/me",
    {
      display_name: name,
      biography:
        "Exploring games, sharing stories, finding people to play with.",
    },
    "PATCH",
  );
  await write(
    page,
    "/me/privacy",
    {
      profile: "public",
      library: "public",
      playtime: "public",
      achievements: "public",
      presence: "connections",
      discovery: true,
      connection_requests: "discoverable",
      messaging: "connections",
    },
    "PATCH",
  );
  await page.goto("/account/steam");
  await page
    .getByRole("button", { name: "Sync my Steam data", exact: true })
    .click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  return (await (await page.request.get("/api/v1/me")).json()).handle as string;
}
async function capture(page: Page, name: string) {
  await page.bringToFront();
  await expect(page.locator("main")).toBeVisible();
  await expect(
    page.getByText("Loading saved results…", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Checking available actions…", { exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // Isolated synthetic test identities only; these images are not portfolio assets.
  await page.screenshot({
    path: `test-results/ui-fixture-${name}.png`,
    fullPage: false,
  });
  if (process.env.BUI_CAPTURE_DIR)
    await saveVisual(page, process.env.BUI_CAPTURE_DIR, name);
}

test("gaming community layout keeps authorized data and desktop/mobile controls accessible", async ({
  browser,
}) => {
  test.setTimeout(90000);
  const a = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const b = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  try {
    await steam(a, identity());
    await steam(b, identity());
    const pa = await a.newPage(),
      pb = await b.newPage();
    await login(pa);
    await login(pb);
    const ha = await prepare(pa, "Portfolio player A"),
      hb = await prepare(pb, "Portfolio player B");
    await pa.getByLabel("Game for achievements").selectOption("77730001");
    await pa
      .getByRole("button", { name: "Sync selected game achievements" })
      .click();
    await expect(pa.getByText("Achievement job: succeeded")).toBeVisible({
      timeout: 15000,
    });
    const before = await (
      await pa.request.get("/api/v1/me/steam/sync-status")
    ).json();
    await pa.goto(`/users/${ha}`);
    await expect(
      pa.getByRole("heading", { name: "Gaming identity" }),
    ).toBeVisible();
    await expect(
      pa.getByRole("navigation", { name: "Main navigation" }),
    ).toBeVisible();
    const snapshotHelp = pa
      .locator(".gaming-identity-card")
      .getByText("Snapshot details", { exact: true });
    await snapshotHelp.click();
    const helpBox = await pa.locator(".gaming-card-heading").boundingBox();
    const statsBox = await pa
      .locator(".gaming-identity-card .player-stats")
      .boundingBox();
    expect(statsBox!.y).toBeGreaterThanOrEqual(helpBox!.y + helpBox!.height);
    await snapshotHelp.click();
    await capture(pa, "profile-desktop");
    await pa.goto(`/users/${ha}/games`);
    await expect(pa.getByText("27 visible matching games")).toBeVisible();
    await capture(pa, "library-desktop");
    await pa.getByRole("link", { name: "Achievements", exact: true }).click();
    await expect(pa.getByText("1 visible matching games")).toBeVisible();
    await expect(pa.getByLabel("With achievement data")).toBeChecked();
    await pa.goto(`/users/${ha}/games/77730001`);
    await expect(
      pa.getByRole("progressbar", { name: "Selected game completion" }),
    ).toHaveAttribute("value", "50");
    await capture(pa, "achievements-desktop");
    await pa.goto("/discover");
    await expect(pa.locator(".discovery-player").first()).toBeVisible();
    await pa.getByText("Why this player?", { exact: true }).first().click();
    await expect(
      pa
        .getByText("Based on saved visible evidence, not a skill rating.")
        .first(),
    ).toBeVisible();
    await pa.getByText("Why this player?", { exact: true }).first().click();
    await expect(
      pa.getByText("Checking available actions…", { exact: true }),
    ).toHaveCount(0);
    await capture(pa, "discover-desktop");
    await pa.goto(`/users/${hb}`);
    const menu = pa.getByLabel("More player actions", { exact: true });
    await menu.focus();
    await pa.keyboard.press("Enter");
    await expect(
      pa.getByRole("menuitem", { name: "Block player", exact: true }),
    ).toBeVisible();
    await pa.keyboard.press("Escape");
    await expect(menu).toBeFocused();
    await expect(
      pa.getByRole("menuitem", { name: "Block player", exact: true }),
    ).toBeHidden();
    await menu.click();
    await pa
      .getByRole("menuitem", { name: "Block player", exact: true })
      .click();
    await expect(pa.getByRole("dialog")).toBeVisible();
    await expect(
      pa.getByRole("button", {
        name: "Keep current relationship",
        exact: true,
      }),
    ).toBeFocused();
    await pa.keyboard.press("Escape");
    await expect(pa.getByRole("dialog")).toBeHidden();
    const request = await (
      await write(pa, "/connection-requests", { handle: hb })
    ).json();
    await write(pb, `/connection-requests/${request.id}/accept`);
    const conv = await (
      await write(pa, "/conversations/direct", { handle: hb })
    ).json();
    await pa.goto(`/messages?conversation=${conv.id}`);
    await pb.goto(`/messages?conversation=${conv.id}`);
    await expect(pa.getByLabel("Message text", { exact: true })).toBeEnabled();
    await pa
      .getByLabel("Message text", { exact: true })
      .fill("A neutral message from an isolated test fixture.");
    await pa.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(pa.getByLabel("Message text", { exact: true })).toBeFocused();
    await expect(
      pb
        .getByLabel("Message history")
        .getByText("A neutral message from an isolated test fixture."),
    ).toBeVisible();
    await pb
      .getByLabel("Message text", { exact: true })
      .fill("Received. The conversation stays in the test database.");
    await pb.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(
      pa
        .getByLabel("Message history")
        .getByText("Received. The conversation stays in the test database."),
    ).toBeVisible();
    await capture(pa, "messages-desktop");
    await pa.setViewportSize({ width: 1280, height: 800 });
    await capture(pa, "messages-1280");
    await pa.setViewportSize({ width: 390, height: 844 });
    await expect(
      pa.getByRole("button", { name: "Back to conversations", exact: true }),
    ).toBeVisible();
    await pa
      .getByRole("button", { name: "Back to conversations", exact: true })
      .click();
    await expect(
      pa.getByRole("heading", { name: "Your conversations" }),
    ).toBeVisible();
    await pa
      .locator(".chat-conversation")
      .filter({ hasText: "Portfolio player B" })
      .click();
    await expect(pa.getByLabel("Message text", { exact: true })).toBeVisible();
    await capture(pa, "messages-mobile");
    // Long synthetic text exercises scrolling without adding production data.
    await write(pb, `/conversations/${conv.id}/messages`, {
      client_message_id: crypto.randomUUID(),
      body: Array.from(
        { length: 45 },
        (_, i) => `Saved test line ${i + 1}`,
      ).join("\n"),
    });
    const history = pa.getByLabel("Message history");
    await expect(history.getByText(/Saved test line 45/)).toBeVisible();
    await expect
      .poll(() =>
        history.evaluate(
          (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
        ),
      )
      .toBeLessThan(72);
    await history.evaluate((el) => {
      el.scrollTop = 0;
    });
    await expect(
      pa.getByRole("button", { name: "Jump to latest" }),
    ).toBeVisible();
    await write(pb, `/conversations/${conv.id}/messages`, {
      client_message_id: crypto.randomUUID(),
      body: "A new arrival while reading older history.",
    });
    await expect(
      history.getByText("A new arrival while reading older history."),
    ).toBeAttached();
    expect(await history.evaluate((el) => el.scrollTop)).toBeLessThan(10);
    await pa.getByRole("button", { name: "Jump to latest" }).click();
    await expect
      .poll(() =>
        history.evaluate(
          (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
        ),
      )
      .toBeLessThan(72);
    await expect(
      pa.getByRole("button", { name: "Jump to latest" }),
    ).toBeHidden();
    await pa.goto(`/users/${ha}`);
    await expect(
      pa.getByRole("heading", { name: "Gaming identity" }),
    ).toBeVisible();
    await capture(pa, "profile-mobile");
    await pa.setViewportSize({ width: 1280, height: 800 });
    await capture(pa, "profile-1280");
    await pa.setViewportSize({ width: 1440, height: 900 });
    await pa.goto("/account/privacy");
    await expect(pa.getByLabel("Profile visibility")).toHaveText(
      "Public (signed-in players)",
    );
    await capture(pa, "privacy-desktop");
    for (const path of ["/connections", "/notifications"]) {
      await pa.goto(path);
      await expect(pa.getByRole("heading", { level: 1 })).toBeVisible();
      await capture(pa, path.slice(1) + "-desktop");
    }
    for (const width of [1280, 820, 390]) {
      await pa.setViewportSize({ width, height: 900 });
      await pa.goto("/discover");
      await expect(pa.locator(".discovery-player").first()).toBeVisible();
      await capture(pa, `discover-${width}`);
      if (width === 390) {
        await expect(
          pa
            .getByRole("navigation", { name: "Main navigation" })
            .getByRole("link", { name: "Library", exact: true }),
        ).toBeVisible();
        await expect(
          pa
            .getByRole("navigation", { name: "Account navigation" })
            .getByRole("link", { name: "Notifications", exact: true }),
        ).toBeVisible();
      }
    }
    expect(
      (await (await pa.request.get("/api/v1/me/steam/sync-status")).json())
        .latest_job,
    ).toEqual(before.latest_job);
  } finally {
    await a.close();
    await b.close();
  }
});
