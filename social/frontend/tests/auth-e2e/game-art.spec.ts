import { expect, test } from "@playwright/test";

test.use({ deviceScaleFactor: 2 });

test("large artwork, compact icons and deterministic 404 fallbacks preserve authorized page data", async ({
  page,
}) => {
  const state = {
    status: "populated",
    data_available: true,
    stale: false,
    last_success_at: "2026-10-25T10:00:00Z",
    in_progress: false,
  };
  const ids = [3576350, 77870002, 77870003, 77870004];
  const games = ids.map((app_id, index) => ({
    app_id,
    name: [
      "Available library artwork",
      "Icon fallback",
      "Unavailable artwork",
      "Header fallback",
    ][index],
    total_minutes: 456 - index * 80,
    recent_minutes: null,
    last_played_at: null,
    visual: {
      source: "steam",
      card_url: `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${app_id}/library_hero.jpg`,
      thumbnail_url: `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${app_id}/header.jpg`,
      icon_url: `https://media.steampowered.com/steamcommunity/public/images/apps/${app_id}/${"b".repeat(40)}.jpg`,
    },
    achievements: {
      state: { ...state, status: "never", data_available: false },
      coverage: "unknown",
      definition_count: null,
      known_unlocked: null,
      known_locked: null,
      completion_percent: null,
    },
  }));
  const profile = {
    handle: "art_owner",
    display_name: "Artwork test",
    biography: "",
    is_owner: true,
    persona_name: null,
    profile_state: state,
    library_state: state,
    recent_state: state,
    playtime_visible: true,
    achievements_visible: true,
    game_count: 4,
    total_minutes: 1344,
    synchronized_achievement_games: 0,
    most_played: games,
    recent_games: [games[0]],
  };
  const requests: { path: string; method: string }[] = [];
  const artRequests: string[] = [];
  const unexpected: string[] = [];
  await page.route(/^https?:\/\/(?!127\.0\.0\.1:3200\/)/, async (route) => {
    const url = new URL(route.request().url());
    if (
      !["shared.fastly.steamstatic.com", "media.steampowered.com"].includes(
        url.hostname,
      )
    ) {
      unexpected.push(url.hostname);
      await route.abort();
      return;
    }
    artRequests.push(url.pathname);
    const id = Number(url.pathname.split("/").at(-2));
    const icon = url.hostname === "media.steampowered.com";
    const found = icon
      ? id !== 77870003
      : (id === 3576350 && url.pathname.endsWith("library_hero.jpg")) ||
        (id === 77870004 && url.pathname.endsWith("header.jpg"));
    // Synthetic bytes only; no remote image or Steam request is performed by this test.
    await route.fulfill(
      found
        ? {
            contentType: "image/svg+xml",
            body: `<svg xmlns="http://www.w3.org/2000/svg" width="${icon ? 48 : 1920}" height="${icon ? 48 : 620}"><rect width="100%" height="100%" fill="#315666"/></svg>`,
          }
        : { status: 404, body: "Unavailable synthetic asset" },
    );
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    requests.push({ path, method: route.request().method() });
    let data: unknown = {};
    if (path === "/me") data = { ...profile, status: "active" };
    else if (path === "/users/art_owner") data = profile;
    else if (path === "/users/art_owner/games")
      data = {
        state,
        playtime_visible: true,
        total: 4,
        items: games,
        next_cursor: null,
      };
    else if (path.startsWith("/discovery/"))
      data = {
        policy: "visible-evidence-v1",
        items: path.endsWith("steam-friends")
          ? []
          : [
              {
                person: { handle: "art_peer", display_name: "Artwork peer" },
                score: 10,
                mutual_games: 1,
                recent_overlap: 0,
                reasons: ["You both have 1 visible games"],
                steam_friend: false,
              },
            ],
      };
    else if (path === "/users/art_peer")
      data = {
        ...profile,
        handle: "art_peer",
        display_name: "Artwork peer",
        is_owner: false,
      };
    else if (path.endsWith("/comparison"))
      data = {
        status: "available",
        left_library_state: state,
        right_library_state: state,
        left_handle: "art_owner",
        right_handle: "art_peer",
        items: [
          {
            ...games[0],
            left_achievements: games[0].achievements,
            right_achievements: games[0].achievements,
          },
        ],
        mutual_count: 1,
      };
    else if (path.endsWith("/relationship"))
      data = { status: "none", can_request: true, request_id: null };
    else {
      await route.fulfill({
        status: 404,
        json: { error: { code: "UNEXPECTED_FIXTURE_ROUTE" } },
      });
      return;
    }
    await route.fulfill({ json: data });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/users/art_owner");
  const featured = page.locator(".identity-games .game-art");
  await expect(featured.first()).toHaveAttribute("data-variant", "card");
  await expect(featured.first()).toHaveAttribute("data-image-kind", "library");
  await expect(featured.nth(1)).toHaveAttribute("data-image-kind", "icon");
  await expect(featured.nth(2)).toHaveAttribute("data-image-kind", "fallback");
  await expect(
    page.locator(".player-game-list .game-art").first(),
  ).toHaveAttribute("data-variant", "thumbnail");
  await expect(
    page.locator(".player-game-list .game-art").first(),
  ).toHaveAttribute("data-image-kind", "library");
  // Both Most Played and populated Recent use the same canonical 48px renderer.
  await expect(page.locator(".player-game-list")).toHaveCount(2);
  await expect(
    page.locator(".player-game-list").nth(1).locator(".game-art"),
  ).toHaveAttribute("data-variant", "thumbnail");
  const thumbnailImage = page
    .locator(".player-game-list .game-art img")
    .first();
  expect(await page.evaluate(() => devicePixelRatio)).toBe(2);
  expect(
    await thumbnailImage.evaluate((img: HTMLImageElement) => ({
      width: img.naturalWidth,
      height: img.naturalHeight,
      srcset: img.srcset,
    })),
  ).toEqual({ width: 1920, height: 620, srcset: "" });
  const smallFallback = page
    .locator(".player-game-list")
    .first()
    .locator('.game-art[data-image-kind="icon"] img');
  expect((await smallFallback.boundingBox())!.width).toBeLessThanOrEqual(32);
  const compact = await page
    .locator(".player-game-list .game-art img")
    .first()
    .boundingBox();
  expect(compact!.width).toBeLessThanOrEqual(48);
  expect(compact!.height).toBeLessThanOrEqual(48);
  await page.getByRole("link", { name: "Library", exact: true }).click();
  const cards = page.locator(".library-game-card > .game-art");
  await expect(cards).toHaveCount(4);
  for (const [index, kind] of [
    "library",
    "icon",
    "fallback",
    "header",
  ].entries())
    await expect(cards.nth(index)).toHaveAttribute("data-image-kind", kind);
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const box = await cards.first().boundingBox();
    expect(box!.width / box!.height).toBeCloseTo(460 / 215, 1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  const fallbackIcon = await cards.nth(1).locator("img").boundingBox();
  expect(fallbackIcon!.width).toBeLessThanOrEqual(48);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("link", { name: "Discover", exact: true }).click();
  const chip = page.locator(".mutual-games .game-art").first();
  await expect(chip).toHaveAttribute("data-variant", "thumbnail");
  await expect(chip.locator("img")).toHaveAttribute(
    "src",
    games[0].visual.card_url,
  );
  const chipBox = await chip.boundingBox();
  expect(chipBox!.width).toBe(36);
  expect(chipBox!.height).toBe(36);
  expect(
    artRequests
      .filter((p) => p.includes("/3576350/"))
      .every((p) => p.endsWith("/library_hero.jpg")),
  ).toBe(true);
  await page.goto("/users/art_peer/compare");
  const comparison = page.locator(".comparison-game-name .game-art").first();
  await expect(comparison).toHaveAttribute("data-variant", "thumbnail");
  await expect(comparison).toHaveAttribute("data-image-kind", "library");
  const comparisonBox = await comparison.boundingBox();
  expect(comparisonBox!.width).toBe(44);
  expect(comparisonBox!.height).toBe(44);
  expect(
    requests.every((r) => r.method === "GET" && !r.path.includes("sync")),
  ).toBe(true);
  expect(unexpected).toEqual([]);
});
