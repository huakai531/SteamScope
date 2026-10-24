import { expect, test, type Page } from "@playwright/test";
import { saveVisual } from "./visual-capture";
import { join } from "node:path";

// Browser-only visual samples. No persisted users, live Steam or real messages.
const state = {
  status: "populated",
  data_available: true,
  stale: false,
  last_success_at: "2026-10-23T20:00:00Z",
  in_progress: false,
};
const games = [
  {
    app_id: 900000001,
    name: "Orbit Relay",
    total_minutes: 1272,
    recent_minutes: 135,
  },
  {
    app_id: 900000002,
    name: "Mosslight Vale",
    total_minutes: 948,
    recent_minutes: null,
  },
  {
    app_id: 900000003,
    name: "Ember Circuit",
    total_minutes: 720,
    recent_minutes: 48,
  },
].map((game, index) => ({
  ...game,
  last_played_at: "2026-10-23T20:00:00Z",
  achievements: {
    state: index ? { ...state, status: "never", data_available: false } : state,
    coverage: index ? "unknown" : "complete",
    definition_count: index ? null : 51,
    known_unlocked: index ? null : 24,
    known_locked: index ? null : 27,
    completion_percent: index ? null : 47.06,
  },
}));
const profile = {
  handle: "visual_alex",
  display_name: "Alex Morgan",
  biography:
    "Co-op puzzles, indie worlds, and a good story. Always up for one more run.",
  is_owner: true,
  persona_name: "alexplays",
  profile_state: state,
  library_state: state,
  recent_state: state,
  playtime_visible: true,
  achievements_visible: true,
  game_count: 3,
  total_minutes: 2940,
  synchronized_achievement_games: 1,
  most_played: games,
  recent_games: [games[0], games[2]],
};
const cid = "00000000-0000-4000-8000-000000000001";
const messages = [
  {
    body: "You play Orbit Relay too?",
    mine: false,
    created_at: "2026-10-22T20:30:00Z",
  },
  {
    body: "Yes! Still one of my favourite co-op games.",
    mine: true,
    created_at: "2026-10-22T20:31:00Z",
  },
  {
    body: "Want to try the community chambers this weekend?",
    mine: false,
    created_at: "2026-10-23T20:30:00Z",
  },
  {
    body: "I'm in. Saturday evening works for me.",
    mine: true,
    created_at: "2026-10-23T20:31:00Z",
  },
  { body: "Around 8?", mine: true, created_at: "2026-10-23T20:31:30Z" },
  {
    body: "Perfect. I'll find a few good maps.",
    mine: false,
    created_at: "2026-10-23T20:32:00Z",
  },
].map((message, index) => ({
  ...message,
  id: `visual-message-${index}`,
  sequence: index + 1,
  deleted_at: null,
}));

async function fixture(page: Page) {
  const requests: string[] = [];
  const external: string[] = [];
  await page.route(/^https?:\/\/(?!127\.0\.0\.1:3200\/)/, async (route) => {
    external.push(new URL(route.request().url()).hostname);
    await route.abort();
  });
  const conversation = {
    id: cid,
    person: { handle: "visual_jun", display_name: "Jun" },
    can_send: true,
    created_at: messages[0].created_at,
    last_message_at: messages.at(-1)!.created_at,
    last_message: messages.at(-1),
    unread_count: 0,
    last_read_sequence: 6,
    peer_read_sequence: 6,
    latest_sequence: 6,
  };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    requests.push(route.request().method() + " " + path);
    let data: unknown;
    let status = 200;
    if (path === "/me") data = { ...profile, status: "active" };
    else if (path === "/users/visual_alex") data = profile;
    else if (path === "/users/visual_alex/games/900000001")
      data = {
        handle: profile.handle,
        library_state: state,
        playtime_visible: true,
        game: games[0],
      };
    else if (path === "/users/visual_alex/games/900000001/achievements")
      data = {
        state,
        progress: games[0].achievements,
        items: [
          {
            api_name: "visual_unlocked",
            display_name: "First Signal",
            description: "Activate the first relay.",
            state: "unlocked",
            unlock_time: "2026-10-22T20:00:00Z",
          },
          {
            api_name: "visual_locked",
            display_name: "Relay Partner",
            description: "Finish a shared route.",
            state: "locked",
            unlock_time: null,
          },
        ],
        next_cursor: null,
      };
    else if (path === "/conversations")
      data = { items: [conversation], next_cursor: null };
    else if (path === `/conversations/${cid}`) data = conversation;
    else if (path === `/conversations/${cid}/messages`)
      data = { items: messages, next_before: null, next_after: null };
    else {
      status = 404;
      data = { error: { code: "TEST_UNEXPECTED_PATH" } };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.routeWebSocket("**/api/v1/ws", (ws) => {
    ws.onMessage((raw) => {
      const event = JSON.parse(String(raw));
      if (event.type === "watch" && event.conversation_id === cid)
        ws.send(
          JSON.stringify({
            v: 1,
            type: "conversation.state",
            conversation_id: cid,
            can_send: true,
            presence: "online",
            typing: false,
            peer_read_sequence: 6,
          }),
        );
    });
    ws.send(JSON.stringify({ v: 1, type: "ready" }));
  });
  return { requests, external };
}
async function capture(page: Page, name: string) {
  await expect
    .poll(() =>
      page
        .locator("img")
        .evaluateAll((images) =>
          images.every(
            (image) =>
              (image as HTMLImageElement).complete &&
              (image as HTMLImageElement).naturalWidth > 0,
          ),
        ),
    )
    .toBe(true);
  if (process.env.FPP_CAPTURE_DIR) {
    await saveVisual(page, process.env.FPP_CAPTURE_DIR, name);
    if (name.endsWith("mobile"))
      await page.screenshot({
        path: join(process.env.FPP_CAPTURE_DIR, name + "-full.png"),
        fullPage: true,
      });
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

test("gaming identity uses authorized sample titles, icons and unknown playtime without writes", async ({
  page,
}) => {
  const evidence = await fixture(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/users/visual_alex");
  await expect(
    page.getByRole("heading", { name: "Gaming identity" }),
  ).toBeVisible();
  await expect(page.locator(".identity-games img")).toHaveCount(3);
  await expect(page.locator(".player-stats")).toContainText("49.0");
  await capture(page, "profile-desktop");
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await capture(page, width === 390 ? "profile-mobile" : "profile-tablet");
  }
  // Missing playtime is still unknown, including with a real game image.
  await page.route("**/api/v1/users/visual_alex", (route) =>
    route.fulfill({ json: { ...profile, recent_games: [games[1]] } }),
  );
  await page.reload();
  await expect(page.locator(".player-columns section").last()).toContainText(
    "Unknown",
  );
  expect(evidence.requests.every((request) => request.startsWith("GET "))).toBe(
    true,
  );
  expect(evidence.requests.some((request) => request.includes("sync"))).toBe(
    false,
  );
  expect(evidence.external).toEqual([]);
});

test("messenger has local day separators, grouped messages, quiet status and accessible actions", async ({
  page,
}) => {
  const evidence = await fixture(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/messages?conversation=${cid}`);
  await expect(page.getByLabel("Message text", { exact: true })).toBeEnabled();
  await expect(page.locator(".chat-layout")).toHaveAttribute(
    "data-connection",
    "Connected",
  );
  await expect(page.locator(".chat-connection")).toHaveCount(0);
  await expect(page.locator(".conversation-presence")).toContainText("Online");
  await expect(page.locator(".chat-day")).toHaveCount(2);
  await expect(
    page.locator('[data-message-id="visual-message-4"]'),
  ).toHaveAttribute("data-group-start", "false");
  await expect(
    page.locator('[data-message-id="visual-message-4"] time'),
  ).toHaveAttribute("title", /2026/);
  const workspace = await page.locator(".chat-layout").boundingBox();
  expect(workspace!.height).toBeGreaterThan(800);
  const bubble = await page
    .locator('[data-message-id="visual-message-2"]')
    .boundingBox();
  const canvas = await page.locator(".chat-history").boundingBox();
  expect(bubble!.width / canvas!.width).toBeLessThanOrEqual(0.65);
  await capture(page, "messages-desktop");
  await page.getByRole("button", { name: "Conversation actions" }).click();
  await expect(
    page.getByRole("menuitem", { name: "View profile" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Conversation actions" }),
  ).toBeFocused();
  await page.getByLabel("Message text", { exact: true }).focus();
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await expect
      .poll(() =>
        page
          .locator(".chat-history")
          .evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight),
      )
      .toBeLessThan(3);
    await capture(page, width === 390 ? "messages-mobile" : "messages-tablet");
    const composer = await page
      .getByLabel("Message text", { exact: true })
      .boundingBox();
    expect(composer!.y + composer!.height).toBeLessThan(
      width === 390 ? 780 : 900,
    );
  }
  // A real reading position remains distinct from resize-induced scrolling.
  await page.locator(".chat-history").evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect(
    page.getByRole("button", { name: "Jump to latest" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 800 });
  await expect
    .poll(() => page.locator(".chat-history").evaluate((el) => el.scrollTop))
    .toBeLessThan(3);
  await page.getByRole("button", { name: "Jump to latest" }).click();
  await expect
    .poll(() =>
      page
        .locator(".chat-history")
        .evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight),
    )
    .toBeLessThan(3);
  await page.getByRole("button", { name: "Back to conversations" }).click();
  await capture(page, "messages-list-mobile");
  await expect(page.locator(".conversation-time")).toBeVisible();
  expect(evidence.requests.every((request) => request.startsWith("GET "))).toBe(
    true,
  );
  expect(evidence.external).toEqual([]);
});
