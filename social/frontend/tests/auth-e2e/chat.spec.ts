import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { identity, login, steam } from "./helpers";

test("invalid socket query is promptly rejected through the real Next upgrade proxy", async ({
  page,
}) => {
  await page.goto("/login");
  const promptlyRejected = await page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const url = new URL("/api/v1/ws?unsupported=1", location.origin);
        url.protocol = "ws:";
        const ws = new WebSocket(url);
        const timer = setTimeout(() => {
          resolve(false);
          ws.close();
        }, 3000);
        ws.onerror = () => {
          clearTimeout(timer);
          resolve(true);
        };
        ws.onopen = () => {
          clearTimeout(timer);
          resolve(false);
          ws.close();
        };
      }),
  );
  expect(promptlyRejected).toBe(true);
});

async function write(
  page: Page,
  path: string,
  data?: unknown,
  method = "POST",
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
async function setup(page: Page, name: string) {
  await write(page, "/me", { display_name: name }, "PATCH");
  await write(
    page,
    "/me/privacy",
    {
      profile: "public",
      presence: "connections",
      discovery: true,
      connection_requests: "discoverable",
      messaging: "connections",
    },
    "PATCH",
  );
  return (await (await page.request.get("/api/v1/me")).json()).handle as string;
}
async function open(page: Page, handle: string) {
  await page.goto("/messages");
  await expect(page.locator(".chat-layout")).toHaveAttribute(
    "data-connection",
    "Connected",
  );
  await page.getByText("Open a conversation", { exact: true }).click();
  await page.getByLabel("Connection handle", { exact: true }).fill(handle);
  await page
    .getByRole("button", { name: "Open conversation", exact: true })
    .click();
  await expect(page.getByLabel("Message text", { exact: true })).toBeEnabled();
}
async function send(page: Page, text: string) {
  await page.getByLabel("Message text", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByLabel("Message text", { exact: true })).toHaveValue(
    "",
  );
}

test("two users real sockets persist recover retry read delete report and revoke on block", async ({
  browser,
}) => {
  test.setTimeout(60000); // Two logins plus bounded reconnect/revocation checks in one end-to-end flow.
  const a = await browser.newContext(),
    b = await browser.newContext();
  try {
    await steam(a, identity());
    await steam(b, identity());
    const pa = await a.newPage(),
      pb = await b.newPage();
    await login(pa);
    await login(pb);
    const ha = await setup(pa, "Chat Alice"),
      hb = await setup(pb, "Chat Bob");
    const request = (
      await (await write(pa, "/connection-requests", { handle: hb })).json()
    ).id;
    await write(pb, `/connection-requests/${request}/accept`);
    let realtimeMessages = 0;
    pb.on("websocket", (ws) =>
      ws.on("framereceived", (frame) => {
        if (
          String(frame.payload).includes('"type":"message.created"') ||
          String(frame.payload).includes('"type": "message.created"')
        )
          realtimeMessages++;
      }),
    );
    await open(pa, hb);
    await open(pb, ha);
    const text = "Hello 🎮 <b>plain text</b> {a,b}";
    await send(pa, text);
    await expect(
      pb.getByLabel("Message history").getByText(text, { exact: true }),
    ).toBeVisible();
    expect(realtimeMessages).toBeGreaterThan(0);
    await send(pb, "Reply from Bob");
    await expect(
      pa
        .getByLabel("Message history")
        .getByText("Reply from Bob", { exact: true }),
    ).toBeVisible();
    await expect(
      pa.getByLabel("Message history").getByText(/· Read/),
    ).toBeVisible();
    await pa.reload();
    await pb.reload();
    await expect(
      pa
        .getByLabel("Message history")
        .getByText("Reply from Bob", { exact: true }),
    ).toBeVisible();
    await expect(
      pb.getByLabel("Message history").getByText(text, { exact: true }),
    ).toBeVisible();
    await pa.getByLabel("Message text", { exact: true }).fill("Draft only");
    await expect(
      pb.getByText("Chat Alice is typing…", { exact: true }),
    ).toBeVisible();
    await pa.getByLabel("Message text", { exact: true }).fill("");
    await expect(
      pb.getByText("Chat Alice is typing…", { exact: true }),
    ).toHaveCount(0);
    // Drop the actual socket/network, then recover from the durable after cursor.
    await b.setOffline(true);
    await send(pa, "Missed while offline");
    await b.setOffline(false);
    await expect(
      pb
        .getByLabel("Message history")
        .getByText("Missed while offline", { exact: true }),
    ).toBeVisible({ timeout: 15000 });
    const cid = new URL(pa.url()).searchParams.get("conversation")!;
    // Drop the HTTP acknowledgement after persistence, then use the actual UI retry.
    let dropped = false;
    await pa.route(`**/api/v1/conversations/${cid}/messages`, async (route) => {
      if (route.request().method() !== "POST" || dropped) {
        await route.continue();
        return;
      }
      dropped = true;
      await route.fetch();
      await route.abort("connectionfailed");
    });
    await pa
      .getByLabel("Message text", { exact: true })
      .fill("Lost acknowledgement");
    await pa.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(
      pa.getByRole("button", { name: "Retry same message", exact: true }),
    ).toBeEnabled();
    await pa
      .getByRole("button", { name: "Retry same message", exact: true })
      .click();
    await expect(pa.getByLabel("Message text", { exact: true })).toHaveValue(
      "",
    );
    await expect(
      pb
        .getByLabel("Message history")
        .getByText("Lost acknowledgement", { exact: true }),
    ).toHaveCount(1);
    const payload = {
      client_message_id: randomUUID(),
      body: "Retry idempotently",
    };
    const one = await (
      await write(pa, `/conversations/${cid}/messages`, payload)
    ).json();
    const two = await (
      await write(pa, `/conversations/${cid}/messages`, payload)
    ).json();
    expect(one.id).toBe(two.id);
    await expect(
      pb.getByLabel("Message history").getByText(payload.body, { exact: true }),
    ).toHaveCount(1);
    const bobMessage = pa
      .getByLabel("Message history")
      .getByRole("listitem")
      .filter({ hasText: "Reply from Bob" });
    await bobMessage.getByLabel("Message actions", { exact: true }).click();
    await pa
      .getByRole("menuitem", { name: "Report message", exact: true })
      .click();
    await pa
      .getByRole("combobox", { name: "Report reason", exact: true })
      .selectOption("spam");
    await pa
      .getByLabel("Report description", { exact: true })
      .fill("Synthetic report");
    await pa
      .getByRole("button", { name: "Submit message report", exact: true })
      .click();
    await expect(
      pa.getByText(
        "Message report received. The other player is not notified.",
      ),
    ).toBeVisible();
    await pa
      .getByLabel("Message history")
      .getByRole("listitem")
      .filter({ hasText: text })
      .getByLabel("Message actions", { exact: true })
      .click();
    await pa
      .getByRole("menuitem", { name: "Delete message", exact: true })
      .click();
    await expect(
      pa.getByRole("dialog", { name: "Delete this message?" }),
    ).toBeVisible();
    await pa
      .getByRole("dialog")
      .getByRole("button", { name: "Delete message", exact: true })
      .click();
    await expect(
      pb.getByLabel("Message history").getByText(text, { exact: true }),
    ).toHaveCount(0);
    await expect(
      pb
        .getByLabel("Message history")
        .getByText("Message deleted", { exact: true }),
    ).toBeVisible();
    await write(pa, `/blocks/${hb}`);
    await expect(
      pa.getByText(
        "Conversation unavailable. Messaging access may have changed.",
        { exact: true },
      ),
    ).toBeVisible({ timeout: 8000 });
    await expect(
      pb.getByText(
        "Conversation unavailable. Messaging access may have changed.",
        { exact: true },
      ),
    ).toBeVisible({ timeout: 8000 });
    await expect(pb.getByLabel("Message text", { exact: true })).toHaveCount(0);
    await expect(
      pb.getByText("Chat Alice is typing…", { exact: true }),
    ).toHaveCount(0);
  } finally {
    await a.close();
    await b.close();
  }
});

test("owner messages stays truthfully empty and reads never enqueue Steam work", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  try {
    await steam(context, identity());
    const page = await context.newPage();
    await login(page);
    const before = await (
      await page.request.get("/api/v1/me/steam/sync-status")
    ).json();
    let writes = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && /steam.*sync/.test(r.url())) writes++;
    });
    await page.goto("/messages");
    await expect(
      page.getByText(
        "No conversations yet. Connect with another SteamScope player to start chatting.",
      ),
    ).toBeVisible();
    await page.reload();
    await expect(page.locator(".chat-layout")).toHaveAttribute(
      "data-connection",
      "Connected",
    );
    const after = await (
      await page.request.get("/api/v1/me/steam/sync-status")
    ).json();
    expect(after).toEqual(before);
    expect(writes).toBe(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await expect(
      page.getByRole("button", { name: /voice|video|attach/i }),
    ).toHaveCount(0);
  } finally {
    await context.close();
  }
});
