import { expect, test, type Page } from "@playwright/test";
import { identity, login, steam } from "./helpers";

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
async function prepare(page: Page) {
  const account = await (await page.request.get("/api/v1/me")).json();
  await write(page, "/me/privacy", {
    profile: "public",
    library: "connections",
    playtime: "connections",
    achievements: "connections",
    discovery: true,
    connection_requests: "discoverable",
  });
  await page.goto("/account/steam");
  await page
    .getByRole("button", { name: "Sync my Steam data", exact: true })
    .click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  return account.handle as string;
}

test("two isolated users request accept unlock connections-only data and block", async ({
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
    const ha = await prepare(pa),
      hb = await prepare(pb);
    await pa.goto("/discover");
    await pa.getByLabel("Search handle or display name").fill(hb);
    await pa
      .getByRole("button", { name: "Search players", exact: true })
      .click();
    await pa.getByRole("link", { name: new RegExp(hb) }).click();
    await expect(
      pa.getByText("Not shared or unavailable", { exact: true }),
    ).toBeVisible();
    await pa
      .getByRole("button", { name: "Send connection request", exact: true })
      .click();
    await expect(
      pa.getByText("Request pending", { exact: true }),
    ).toBeVisible();
    await pb.goto("/notifications");
    await expect(
      pb.getByText("Connection request received", { exact: true }),
    ).toBeVisible();
    await pb.getByRole("button", { name: "Mark read", exact: true }).click();
    await expect(
      pb.getByRole("button", { name: "Mark read", exact: true }),
    ).toHaveCount(0);
    await pb.goto("/connections");
    await pb.getByRole("radio", { name: "Requests", exact: true }).click();
    await pb
      .getByRole("button", { name: "Accept request", exact: true })
      .click();
    await pb.getByRole("radio", { name: "Connections", exact: true }).click();
    await pb.getByLabel("More connection actions", { exact: true }).click();
    await expect(
      pb.getByRole("menuitem", { name: "Remove connection", exact: true }),
    ).toBeVisible();
    await pa.reload();
    await expect(pa.getByText("Connected", { exact: true })).toBeVisible();
    expect(
      (await (await pa.request.get(`/api/v1/users/${hb}`)).json()).game_count,
    ).toBe(27);
    await pa.getByLabel("More player actions", { exact: true }).click();
    await pa
      .getByRole("menuitem", { name: "Block player", exact: true })
      .click();
    await pa
      .getByRole("button", { name: "Confirm block", exact: true })
      .click();
    await expect(
      pa.getByRole("heading", { name: "Player or game unavailable" }),
    ).toBeVisible();
    await pb.goto(`/users/${ha}`);
    await expect(
      pb.getByRole("heading", { name: "Player or game unavailable" }),
    ).toBeVisible();
    await pa.goto("/connections");
    await expect(pa.getByText("No SteamScope connections yet.")).toBeVisible();
    await pa.getByRole("radio", { name: "Blocked", exact: true }).click();
    await pa
      .getByRole("button", { name: "Unblock player", exact: true })
      .click();
    await expect(pa.getByText("You have not blocked anyone.")).toBeVisible();
    expect(
      (await (await pa.request.get(`/api/v1/users/${hb}`)).json()).game_count,
    ).toBeNull();
    await pa.setViewportSize({ width: 390, height: 844 });
    expect(
      await pa.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await pa.screenshot({
      path: "test-results/phase5-social-mobile.png",
      fullPage: true,
    });
  } finally {
    await a.close();
    await b.close();
  }
});

test("reject cancel remove and report remain distinct social actions", async ({
  browser,
}) => {
  const a = await browser.newContext(),
    b = await browser.newContext();
  try {
    await steam(a, identity());
    await steam(b, identity());
    const pa = await a.newPage(),
      pb = await b.newPage();
    pa.setDefaultTimeout(6000);
    pb.setDefaultTimeout(6000);
    await login(pa);
    await login(pb);
    const ha = (await (await pa.request.get("/api/v1/me")).json()).handle;
    const hb = (await (await pb.request.get("/api/v1/me")).json()).handle;
    for (const page of [pa, pb])
      await write(page, "/me/privacy", {
        profile: "public",
        discovery: true,
        connection_requests: "discoverable",
      });
    const send = async () => {
      await pa.goto(`/users/${hb}`);
      await pa
        .getByRole("button", { name: "Send connection request", exact: true })
        .click();
      await expect(
        pa.getByText("Request pending", { exact: true }),
      ).toBeVisible();
    };
    await send();
    await pb.goto("/connections");
    await pb.getByRole("radio", { name: "Requests", exact: true }).click();
    await pb
      .getByRole("button", { name: "Reject request", exact: true })
      .click();
    await expect(pb.getByText("No incoming requests.")).toBeVisible();
    await send();
    await pa
      .getByRole("button", { name: "Cancel request", exact: true })
      .click();
    await expect(
      pa.getByRole("button", { name: "Send connection request", exact: true }),
    ).toBeVisible();
    await send();
    await pb.reload();
    await pb.getByRole("radio", { name: "Requests", exact: true }).click();
    await pb
      .getByRole("button", { name: "Accept request", exact: true })
      .click();
    await pb.getByRole("radio", { name: "Connections", exact: true }).click();
    await pb.getByLabel("More connection actions", { exact: true }).click();
    await expect(
      pb.getByRole("menuitem", { name: "Remove connection", exact: true }),
    ).toBeVisible();
    await pb
      .getByRole("menuitem", { name: "Remove connection", exact: true })
      .click();
    await expect(pb.getByText("No SteamScope connections yet.")).toBeVisible();
    await pb.goto(`/users/${ha}`);
    await pb.getByLabel("More player actions", { exact: true }).click();
    await pb
      .getByRole("menuitem", { name: "Report player", exact: true })
      .click();
    await pb
      .getByRole("combobox", { name: "Reason", exact: true })
      .selectOption("spam");
    await pb
      .getByLabel("Description (optional)")
      .fill("<script>synthetic {x,y}</script>");
    await pb
      .getByRole("button", { name: "Submit report", exact: true })
      .click();
    await expect(pb.getByText(/Report saved for review/)).toBeVisible();
    expect(
      (await (await pb.request.get("/api/v1/blocks")).json()).items,
    ).toEqual([]);
  } finally {
    await a.close();
    await b.close();
  }
});

test("sparse owner pages are truthful and reads do not create sync jobs", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    const before = await (
      await page.request.get("/api/v1/me/steam/sync-status")
    ).json();
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/v1/") && r.method() !== "GET")
        writes.push(r.method());
    });
    await page.goto("/discover");
    await expect(
      page.getByText(
        "No recommendations yet. More players, more games in common.",
      ),
    ).toBeVisible();
    await page
      .getByLabel("Search handle or display name")
      .fill("no_such_fixture_player");
    await page
      .getByRole("button", { name: "Search players", exact: true })
      .click();
    await expect(
      page.getByText("No visible players match this search."),
    ).toBeVisible();
    await page.goto("/connections");
    await page.getByRole("radio", { name: "Requests", exact: true }).click();
    await expect(page.getByText("No incoming requests.")).toBeVisible();
    await page.reload();
    await page.getByRole("radio", { name: "Requests", exact: true }).click();
    await expect(page.getByText("No outgoing requests.")).toBeVisible();
    await page.goto("/notifications");
    await expect(page.getByText("No notifications yet.")).toBeVisible();
    await page
      .getByRole("link", { name: "Player profile", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "New player", exact: true }),
    ).toBeVisible();
    expect(writes).toEqual([]);
    expect(
      (await (await page.request.get("/api/v1/me/steam/sync-status")).json())
        .latest_job,
    ).toEqual(before.latest_job);
  } finally {
    await context.close();
  }
});
