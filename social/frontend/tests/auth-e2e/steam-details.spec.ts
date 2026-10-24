import { expect, test } from "@playwright/test";
import { identity, steam, login } from "./helpers";

test("switching games hides another app's failure and late request feedback", async ({
  browser,
}) => {
  const context = await browser.newContext();
  let release = () => {};
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    await page.getByRole("link", { name: "My Steam Data" }).click();
    await page
      .getByRole("button", { name: "Sync my Steam data", exact: true })
      .click();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 15000,
    });
    await page.route("**/api/v1/me/steam/games/77730001/achievements", (r) =>
      r.fulfill({
        json: {
          app_id: 77730001,
          state: {
            resource: "achievements",
            status: "unavailable",
            code: "ACCESS_DENIED_ACHIEVEMENTS",
            data_available: false,
            last_success_at: null,
          },
          schema_state: {
            language: "english",
            status: "populated",
            code: "OK",
            revision: "a".repeat(64),
            last_success_at: null,
            stale: false,
          },
          latest_job: {
            id: "00000000-0000-4000-8000-000000000001",
            status: "partial",
            scope: "achievements",
            app_id: 77730001,
          },
          coverage: "unknown",
          known_unlocked: null,
          known_locked: null,
          definition_count: 21,
          completion_percent: null,
          items: [],
        },
      }),
    );
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(
      "**/api/v1/me/steam/games/77730001/achievements/sync",
      async (r) => {
        await pending;
        await r.fulfill({
          status: 429,
          json: {
            error: { code: "STEAM_SYNC_COOLDOWN", message: "Fixture cooldown" },
          },
        });
      },
    );
    await page.getByLabel("Game for achievements").selectOption("77730001");
    await expect(page.getByText("Achievement job: partial")).toBeVisible();
    await expect(page.getByText(/Known unlocked: Unknown/)).toBeVisible();
    await expect(
      page.getByText(
        "Unavailable: Steam denied this request; the reason is unconfirmed",
      ),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Sync selected game achievements" })
      .click();
    await page.getByLabel("Game for achievements").selectOption("77730002");
    await expect(
      page.getByText("Achievement job: No job requested"),
    ).toBeVisible();
    release();
    await expect(
      page.getByRole("button", { name: "Sync selected game achievements" }),
    ).toBeEnabled();
    await expect(page.getByText("Achievement job: partial")).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Achievement request feedback" }),
    ).toHaveCount(0);
    await expect(page.getByText(/Achievement task ID:/)).toHaveCount(0);
    await expect(
      page.getByText("Friend-list job: No job requested"),
    ).toBeVisible();
  } finally {
    release();
    await context.close();
  }
});

test("selected-game and friends actions use saved owner pipeline without changing base sync", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    await page.getByRole("link", { name: "My Steam Data" }).click();
    await expect(
      page.getByRole("button", { name: "Sync selected game achievements" }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "Sync my Steam data", exact: true })
      .click();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 15000,
    });
    await page.getByLabel("Game for achievements").selectOption("77730001");
    await expect(
      page.getByText("Achievement job: No job requested"),
    ).toBeVisible();
    await expect(
      page.getByText("Friend-list job: No job requested"),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Sync selected game achievements" })
      .click();
    await expect(page.getByText("Achievement job: succeeded")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByRole("status", { name: "Achievement request feedback" }),
    ).toContainText("Selected-game achievement synchronization requested.");
    const achievementTask = await page
      .getByText(/Achievement task ID:/)
      .textContent();
    await expect(page.getByText(/Selected game completion: 50%/)).toBeVisible();
    await expect(
      page.getByText("Synthetic spoiler", { exact: true }),
    ).toHaveCount(0);
    await page.getByLabel("Reveal hidden achievement spoilers").check();
    await expect(
      page.getByText("Synthetic spoiler", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Sync my Steam friends" }).click();
    await expect(page.getByText("Friend-list job: succeeded")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByRole("status", { name: "Friend-list request feedback" }),
    ).toContainText("Steam friend-list synchronization requested.");
    await expect(
      page.getByRole("status", { name: "Achievement request feedback" }),
    ).not.toContainText("friend-list");
    await expect(page.getByText(/Achievement task ID:/)).toHaveText(
      achievementTask!,
    );
    await page.getByLabel("Game for achievements").selectOption("77730002");
    await expect(
      page.getByText("Achievement job: No job requested"),
    ).toBeVisible();
    await expect(page.getByText(/Achievement task ID:/)).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Achievement request feedback" }),
    ).toHaveCount(0);
    await expect(page.getByText("Friend-list job: succeeded")).toBeVisible();
    await page.getByLabel("Game for achievements").selectOption("77730001");
    await expect(page.getByText(/Achievement task ID:/)).toHaveText(
      achievementTask!,
    );
    await expect(
      page.getByRole("link", { name: "Open Steam profile 76561198000000991" }),
    ).toBeVisible();
    await expect(page.getByText("Friends since: Unknown")).toBeVisible();
    await page.reload();
    await page.getByLabel("Game for achievements").selectOption("77730001");
    await expect(page.getByText(/Selected game completion: 50%/)).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Open Steam profile 76561198000000991" }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "test-results/phase3b-owner-mobile.png",
      fullPage: true,
    });
    await page
      .getByLabel("Type CLEAR STEAM DATA to confirm")
      .fill("CLEAR STEAM DATA");
    await page
      .getByRole("button", { name: "Clear imported Steam data", exact: true })
      .click();
    await expect(page.getByText(/Imported Steam data cleared/)).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Open Steam profile 76561198000000991" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Sync selected game achievements" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Log out", exact: true }).click();
    await expect(page).toHaveURL(/login/);
  } finally {
    await context.close();
  }
});

for (const mode of ["empty", "restricted", "error", "partial"] as const) {
  test(`synthetic ${mode} UI distinguishes coverage and friend privacy`, async ({
    browser,
  }) => {
    const context = await browser.newContext();
    try {
      await steam(context, identity());
      const page = await context.newPage();
      await login(page);
      await page.getByRole("link", { name: "My Steam Data" }).click();
      await page
        .getByRole("button", { name: "Sync my Steam data", exact: true })
        .click();
      await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
        timeout: 15000,
      });
      const state = {
        resource: "achievements",
        status: mode === "restricted" ? "unavailable" : mode,
        code: mode === "restricted" ? "PLAYER_PROGRESS_UNAVAILABLE" : "FIXTURE",
        data_available: mode === "empty" || mode === "partial",
        stale: mode === "error",
      };
      await page.route("**/api/v1/me/steam/games/77730001/achievements", (r) =>
        r.fulfill({
          json: {
            app_id: 77730001,
            state,
            schema_state: {
              status: mode === "empty" ? "empty" : "populated",
              code: "OK",
              revision: "a".repeat(64),
              last_success_at: null,
              stale: mode === "error",
            },
            latest_job: null,
            coverage:
              mode === "empty"
                ? "no_achievements"
                : mode === "partial"
                  ? "partial"
                  : "unknown",
            known_unlocked: null,
            known_locked: null,
            definition_count: mode === "empty" ? 0 : 2,
            completion_percent: null,
            items: [],
          },
        }),
      );
      await page.route("**/api/v1/me/steam/friends", (r) =>
        r.fulfill({
          json: {
            state: {
              ...state,
              resource: "friends",
              code:
                mode === "restricted"
                  ? "FRIENDS_PRIVATE_OR_UNAUTHORIZED"
                  : "FIXTURE",
            },
            latest_job: null,
            total_count: mode === "empty" ? 0 : null,
            items: [],
          },
        }),
      );
      await page.getByLabel("Game for achievements").selectOption("77730001");
      await expect(
        page.getByText(/Selected game completion: Unavailable/),
      ).toBeVisible();
      if (mode === "empty")
        await expect(page.getByText(/Imported Steam friends: 0/)).toBeVisible({
          timeout: 10000,
        });
      if (mode === "restricted")
        await expect(
          page.getByText(/Privacy or another authorization issue may apply/),
        ).toBeVisible({ timeout: 10000 });
      if (mode === "partial")
        await expect(
          page.getByText(/Schema and player coverage are incomplete/),
        ).toBeVisible();
      if (mode === "error")
        await expect(
          page.getByText(/Shared definitions are stale/),
        ).toBeVisible();
      await expect(
        page.getByRole("link", { name: /Open Steam profile 765/ }),
      ).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}
