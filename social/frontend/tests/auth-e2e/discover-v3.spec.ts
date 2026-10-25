import { test, expect, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// Deterministic browser-only fixtures. No accounts, relationships or imports are
// written to either database; unexpected API paths fail closed in this test.
const candidates = [
  {
    handle: "visual_jun",
    display_name: "Jun",
    biography:
      "Co-op adventures, a patient pace, and one more run before calling it a night.",
  },
  {
    handle: "visual_mira",
    display_name: "Mira",
    biography: "Here for clever puzzles and worlds worth getting lost in.",
  },
  {
    handle: "visual_rowan",
    display_name: "Rowan",
    biography: "Good stories. Difficult bosses. Better company.",
  },
  {
    handle: "visual_nico",
    display_name: "Nico",
    biography: "Looking for a co-op partner for the next adventure.",
  },
  {
    handle: "visual_ren",
    display_name: "Ren",
    biography: "Mostly indies, sometimes one more roguelike run.",
  },
];
const state = {
  status: "populated",
  data_available: true,
  stale: false,
  last_success_at: "2026-10-23T12:00:00Z",
  in_progress: false,
};
const games = [
  { app_id: 900000001, name: "Orbit Relay" },
  { app_id: 900000002, name: "Mosslight Vale" },
  { app_id: 900000003, name: "Ember Circuit" },
];

async function fixture(
  page: Page,
  count: number,
  options: {
    relationship?: string;
    comparison?: "hidden" | "error" | "stale";
    blocked?: boolean;
    friends?: boolean;
  } = {},
) {
  let relationship = options.relationship ?? "none";
  const requests: { path: string; method: string }[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace("/api/v1", "");
    requests.push({ path, method: req.method() });
    let data: unknown;
    let status = 200;
    if (path === "/me")
      data = {
        handle: "visual_owner",
        display_name: "Alex",
        biography: "",
        status: "active",
      };
    else if (path === "/auth/csrf")
      data = { csrf_token: "isolated-browser-fixture" };
    else if (path === "/connection-requests" && req.method() === "POST") {
      relationship = "outgoing";
      data = {};
    } else if (path.startsWith("/discovery/"))
      data = {
        policy: "visible-evidence-v1",
        items:
          path.endsWith("steam-friends") && !options.friends
            ? []
            : candidates.slice(0, count).map((person, index) => ({
                person: {
                  handle: person.handle,
                  display_name: person.display_name,
                },
                score: 70 - index * 5,
                mutual_games: 3,
                recent_overlap: 1,
                reasons: [
                  "You both have 3 visible games",
                  "You both recently played 1 visible game",
                  "Similar known playtime in 2 mutual games",
                ],
                steam_friend: options.friends ?? false,
              })),
      };
    else if (path === "/users/search") data = { items: [], next_cursor: null };
    else if (path.endsWith("/relationship")) {
      if (options.blocked) {
        status = 404;
        data = { error: { code: "SOCIAL_UNAVAILABLE", message: "" } };
      } else
        data = {
          status: relationship,
          can_request: relationship === "none",
          request_id: "visual-request",
        };
    } else if (path.endsWith("/comparison")) {
      if (options.comparison === "error") {
        status = 503;
        data = { error: { code: "UNAVAILABLE", message: "" } };
      } else
        data = {
          status: options.comparison === "hidden" ? "unavailable" : "available",
          left_library_state: {
            ...state,
            stale: options.comparison === "stale",
          },
          right_library_state: state,
          items: options.comparison === "hidden" ? [] : games,
          mutual_count: 3,
        };
    } else if (path.startsWith("/users/"))
      data = candidates.find((p) => path === `/users/${p.handle}`) ?? {};
    else {
      status = 404;
      data = { error: { code: "TEST_UNEXPECTED_PATH", message: "" } };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  return requests;
}

async function capture(page: Page, name: string) {
  if (!process.env.DV3_CAPTURE_DIR) return;
  mkdirSync(process.env.DV3_CAPTURE_DIR, { recursive: true });
  await page.screenshot({
    path: join(process.env.DV3_CAPTURE_DIR, name + ".png"),
    fullPage: name.endsWith("390"),
  });
  const html = await page.evaluate(() => {
    const css = Array.from(document.styleSheets)
      .flatMap((s) => {
        try {
          return Array.from(s.cssRules).map((r) => r.cssText);
        } catch {
          return [];
        }
      })
      .join("\n");
    const clone = document.documentElement.cloneNode(true) as HTMLElement;
    clone
      .querySelectorAll("script,style,link,meta,base,nextjs-portal")
      .forEach((e) => e.remove());
    const head = clone.querySelector("head")!;
    const meta = document.createElement("meta");
    meta.httpEquiv = "Content-Security-Policy";
    meta.content =
      "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:";
    head.append(meta);
    const viewport = document.createElement("meta");
    viewport.name = "viewport";
    viewport.content = "width=device-width, initial-scale=1";
    head.append(viewport);
    const style = document.createElement("style");
    style.textContent = css;
    head.append(style);
    return "<!doctype html>" + clone.outerHTML;
  });
  writeFileSync(join(process.env.DV3_CAPTURE_DIR, name + ".html"), html);
}

for (const count of [0, 1, 2, 5]) {
  test(`Discover V3 ${count} players, honest game evidence and responsive layout`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const requests = await fixture(page, count);
    await page.goto("/discover");
    await expect(
      page.getByRole("heading", { name: "Discover players" }),
    ).toBeVisible();
    await expect(page.locator(".discover-player-card")).toHaveCount(count);
    if (count) {
      await expect(page.locator(".mutual-games")).toHaveCount(count);
      await expect(page.locator(".discover-bio").first()).toContainText(
        "Co-op adventures",
      );
      await expect(
        page.getByRole("button", { name: "Connect", exact: true }),
      ).toHaveCount(count);
      await expect(
        page.locator('.mutual-games .game-art[data-variant="thumbnail"]'),
      ).toHaveCount(count * 3);
    } else
      await expect(
        page.getByText("No recommendations yet.", { exact: false }),
      ).toBeVisible();
    await capture(page, `discover-${count}-desktop`);
    if (count === 1) {
      const action = await page
        .getByRole("link", { name: "View profile" })
        .boundingBox();
      expect(action!.y + action!.height).toBeLessThan(900);
      for (const width of [1280, 820, 390]) {
        await page.setViewportSize({
          width,
          height: width === 390 ? 844 : 900,
        });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await capture(page, `discover-1-${width}`);
      }
      await page
        .getByLabel("Search handle or display name")
        .fill("unmatched_player");
      await page.getByRole("button", { name: "Search players" }).click();
      await expect(
        page.getByText("No players found", { exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Clear search" }).click();
      await expect(
        page.getByRole("heading", { name: "Search results" }),
      ).toHaveCount(0);
    }
    expect(requests.every((r) => r.method === "GET")).toBe(true);
    expect(
      requests.some(
        (r) =>
          /steam|sync/.test(r.path) && r.path !== "/discovery/steam-friends",
      ),
    ).toBe(false);
  });
}

test("Discover compact connection states retain authorization and explicit actions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const requests = await fixture(page, 1);
  await page.goto("/discover");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("Requested", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cancel request" }),
  ).toHaveCount(0);
  expect(
    requests.filter((r) => r.method === "POST").map((r) => r.path),
  ).toEqual(["/connection-requests"]);
  await capture(page, "discover-pending");
  for (const relationship of ["incoming", "connected"]) {
    await page.unrouteAll();
    await fixture(page, 1, { relationship, friends: true });
    await page.reload();
    await expect(
      page.getByText(relationship === "incoming" ? "Respond" : "Connected", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".discover-player-card")).toHaveCount(1);
    await expect(
      page.getByText("Your matching Steam friends are included above.", {
        exact: false,
      }),
    ).toBeVisible();
    await capture(page, `discover-${relationship}`);
  }
});

test("Discover never exposes hidden, stale or failed shared-game names", async ({
  page,
}) => {
  for (const comparison of ["hidden", "error", "stale"] as const) {
    await page.unrouteAll();
    await fixture(page, 1, { comparison });
    await page.goto("/discover");
    await expect(page.locator(".discover-bio").first()).toContainText(
      "Co-op adventures",
    );
    await expect(page.locator(".mutual-games")).toHaveCount(0);
    await expect(page.getByText("Orbit Relay", { exact: true })).toHaveCount(0);
  }
});

test("Discover removes a candidate denied by the current relationship authorization", async ({
  page,
}) => {
  await fixture(page, 1, { blocked: true });
  await page.goto("/discover");
  await expect(
    page.getByText("No Steam friends here yet.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".discover-player-card")).toHaveCount(0);
  await expect(page.getByText("Jun", { exact: true })).toHaveCount(0);
});
