import { expect, test, type Page } from "@playwright/test";
import { identity, steam, login } from "./helpers";

async function write(
  page: Page,
  path: string,
  data: unknown,
  method = "PATCH",
) {
  const csrf = await (await page.request.get("/api/v1/auth/csrf")).json();
  const r = await page.request.fetch("/api/v1" + path, {
    method,
    data,
    headers: {
      Origin: "http://127.0.0.1:3200",
      "X-CSRF-Token": csrf.csrf_token,
    },
  });
  expect(r.ok()).toBeTruthy();
  return r;
}
async function seed(page: Page) {
  await page.goto("/account/steam");
  await page
    .getByRole("button", { name: "Sync my Steam data", exact: true })
    .click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  return (await (await page.request.get("/api/v1/me")).json()).handle as string;
}

test("owner profile, library, detail, refresh and mobile read only saved data", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    const handle = await seed(page);
    await page.getByLabel("Game for achievements").selectOption("77730001");
    await page
      .getByRole("button", { name: "Sync selected game achievements" })
      .click();
    await expect(page.getByText("Achievement job: succeeded")).toBeVisible({
      timeout: 15000,
    });
    await write(page, "/me", {
      biography: '<img src=x onerror="alert(1)"> {x,y} <script>test</script>',
    });
    const before = await (
      await page.request.get("/api/v1/me/steam/sync-status")
    ).json();
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.method() !== "GET" && r.url().includes("/api/v1/"))
        writes.push(r.method());
    });
    await page.goto(`/users/${handle}`);
    await expect(
      page.getByRole("heading", { name: "New player", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/Steam identity ·/)).toBeVisible();
    await expect(page.locator(".player-bio")).toContainText("<img src=x");
    await expect(
      page.locator("#player-main img, #player-main script"),
    ).toHaveCount(0);
    await page.getByRole("link", { name: "Game library", exact: true }).click();
    await expect(page.getByText("27 visible matching games")).toBeVisible();
    await page.getByRole("button", { name: "Next page" }).click();
    await page.getByRole("button", { name: "Previous page" }).click();
    await page.getByLabel("Sort games").selectOption("total");
    await page.getByLabel("With achievement data").check();
    await expect(page.getByText("1 visible matching games")).toBeVisible();
    await page.goto(`/users/${handle}/games/77730001`);
    await expect(
      page.getByText("Selected game completion: 50%", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Unlocked", { exact: true })).toBeVisible();
    await page.reload();
    await expect(
      page.getByText("Selected game completion: 50%", { exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: "test-results/phase4-owner-mobile.png",
      fullPage: true,
    });
    expect(writes).toEqual([]);
    const after = await (
      await page.request.get("/api/v1/me/steam/sync-status")
    ).json();
    expect(after.latest_job.id).toBe(before.latest_job.id);
  } finally {
    await context.close();
  }
});

test("two isolated players, privacy changes and logout across tabs", async ({
  browser,
}) => {
  const a = await browser.newContext(),
    b = await browser.newContext();
  try {
    await steam(a, identity());
    await steam(b, identity());
    const pa = await a.newPage(),
      pb = await b.newPage();
    await login(pa);
    await login(pb);
    const ha = await seed(pa),
      hb = await seed(pb);
    await write(pb, "/me/privacy", {
      profile: "public",
      library: "public",
      playtime: "public",
      achievements: "public",
    });
    await pa.goto(`/users/${hb}/compare`);
    await expect(
      pa.getByText(`Comparing @${ha} (you) with @${hb}`),
    ).toBeVisible();
    await expect(
      pa.getByRole("heading", { name: "Mutually visible games" }),
    ).toBeVisible();
    const response = await pa.request.get(`/api/v1/users/${hb}/comparison`);
    expect((await response.json()).mutual_count).toBe(27);
    await write(pb, "/me/privacy", { library: "connections" });
    await pa.getByRole("button", { name: "Reload saved data" }).click();
    await expect(
      pa.getByRole("heading", { name: "Comparison unavailable" }),
    ).toBeVisible();
    await write(pb, "/me/privacy", { profile: "private" });
    await pa.reload();
    await expect(
      pa.getByRole("heading", { name: "Player or game unavailable" }),
    ).toBeVisible();
    const pc = await a.newPage();
    await pc.goto("/account");
    await pa.goto(`/users/${ha}`);
    await expect(
      pa.getByRole("heading", { name: "New player", exact: true }),
    ).toBeVisible();
    await pc.getByRole("button", { name: "Log out", exact: true }).click();
    await expect(pa).toHaveURL(/\/login/);
    await pa.goBack();
    await expect(
      pa.getByRole("heading", { name: "New player", exact: true }),
    ).toHaveCount(0);
  } finally {
    await a.close();
    await b.close();
  }
});

test("new authenticated owner without imports sees unknown and no fabricated totals", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    await page
      .getByRole("link", { name: "Player profile", exact: true })
      .click();
    await expect(
      page.getByText("Not synchronized", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByText("Not shared or unavailable", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Game library", exact: true }).click();
    await expect(
      page.getByText("Saved game rows and counts are unavailable."),
    ).toBeVisible();
  } finally {
    await context.close();
  }
});
