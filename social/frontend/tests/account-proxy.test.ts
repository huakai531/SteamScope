import { afterEach, expect, test, vi } from "vitest";
import { GET, POST, DELETE } from "@/app/api/v1/[...path]/route";

const context = (path: string) => ({
  params: Promise.resolve({ path: path.split("/") }),
});
function makeRequest(url: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (!headers.has("host")) headers.set("host", new URL(url).host);
  return new Request(url, { ...init, headers });
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("avatar proxy preserves binary data and bounds MIME, size, origin and route", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(new Uint8Array([1, 2, 3]), {
      headers: { "Content-Type": "image/webp" },
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  const src = "users/synthetic/avatar/" + "a".repeat(32) + ".webp";
  const response = await GET(
    makeRequest("http://127.0.0.1:3100/api/v1/" + src),
    context(src),
  );
  expect(response.headers.get("content-type")).toBe("image/webp");
  expect(response.headers.get("cache-control")).toContain("no-store");
  expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2, 3]);
  fetcher.mockClear();
  for (const [type, length, origin, status] of [
    ["image/svg+xml", "10", "http://127.0.0.1:3100", 415],
    ["image/png", "6000000", "http://127.0.0.1:3100", 413],
    ["image/png", "10", "https://evil.example", 403],
  ] as const) {
    expect(
      (
        await POST(
          makeRequest("http://127.0.0.1:3100/api/v1/me/avatar", {
            method: "POST",
            headers: {
              "Content-Type": type,
              "Content-Length": length,
              Origin: origin,
            },
            body: "synthetic",
          }),
          context("me/avatar"),
        )
      ).status,
    ).toBe(status);
  }
  expect(fetcher).not.toHaveBeenCalled();
});

test("social proxy permits explicit methods and keeps unknown surfaces closed", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json({ items: [] })));
  vi.stubGlobal("fetch", fetcher);
  const id = "00000000-0000-4000-8000-000000000001";
  for (const path of [
    "conversations",
    `conversations/${id}`,
    `conversations/${id}/messages`,
    "users/search",
    "discovery/players",
    "discovery/steam-friends",
    "connections",
    "blocks",
    "notifications",
    "connection-requests/incoming",
    "users/player_B/relationship",
  ]) {
    expect(
      (
        await GET(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path),
          context(path),
        )
      ).status,
    ).toBe(200);
  }
  for (const path of [
    "conversations/direct",
    `conversations/${id}/messages`,
    `conversations/${id}/read`,
    `messages/${id}/report`,
    "connection-requests",
    `connection-requests/${id}/accept`,
    `connection-requests/${id}/reject`,
    "blocks/player_B",
    "reports",
    "notifications/read-all",
    `notifications/${id}/read`,
  ]) {
    expect(
      (
        await POST(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path, {
            method: "POST",
          }),
          context(path),
        )
      ).status,
    ).toBe(200);
  }
  for (const path of [
    `messages/${id}`,
    "connections/player_B",
    "blocks/player_B",
    `connection-requests/${id}`,
  ]) {
    expect(
      (
        await DELETE(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path, {
            method: "DELETE",
          }),
          context(path),
        )
      ).status,
    ).toBe(200);
  }
  for (const path of [
    "reports",
    "users",
    "messages",
    "connections/player_B/accept",
    "blocks/76561198000000000",
  ]) {
    expect(
      (
        await GET(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path),
          context(path),
        )
      ).status,
    ).toBe(404);
  }
});

test("player proxy permits only bounded handle reads, never arbitrary Steam IDs or writes", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json({ items: [] })));
  vi.stubGlobal("fetch", fetcher);
  for (const path of [
    "users/player_A",
    "users/player_A/games",
    "users/player_A/games/42",
    "users/player_A/games/42/achievements",
    "users/player_A/comparison",
  ]) {
    const response = await GET(
      makeRequest("http://127.0.0.1:3100/api/v1/" + path),
      context(path),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(
      (
        await POST(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path, {
            method: "POST",
          }),
          context(path),
        )
      ).status,
    ).toBe(404);
  }
  for (const path of [
    "users/76561198000000000",
    "users/a",
    "users/player_A/import",
    "users/player_A/games/42/achievements/sync",
    "users/player_A/../me",
  ]) {
    expect(
      (
        await GET(
          makeRequest("http://127.0.0.1:3100/api/v1/" + path),
          context(path),
        )
      ).status,
    ).toBe(404);
  }
  expect(fetcher).toHaveBeenCalledTimes(5);
});

test("proxy preserves separate cookies and redirects without forwarding untrusted proxy headers", async () => {
  vi.stubEnv("INTERNAL_API_URL", "http://api:8000");
  const headers = new Headers({ Location: "http://127.0.0.1:3100/account" });
  headers.append("Set-Cookie", "session-fixture=opaque; Path=/; HttpOnly");
  headers.append(
    "Set-Cookie",
    "binding-fixture=; Path=/api/v1/auth/steam/callback; Max-Age=0",
  );
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 303, headers }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    makeRequest(
      "http://127.0.0.1:3100/api/v1/auth/steam/callback?state=fixture",
      {
        headers: {
          Cookie: "binding-fixture=test",
          "X-Forwarded-Host": "attacker.invalid",
          "X-Forwarded-For": "evil",
        },
      },
    ),
    context("auth/steam/callback"),
  );
  expect(response.headers.getSetCookie()).toHaveLength(2);
  expect(response.headers.get("location")).toBe(
    "http://127.0.0.1:3100/account",
  );
  const [url, options] = fetcher.mock.calls[0];
  expect(String(url)).toBe(
    "http://api:8000/api/v1/auth/steam/callback?state=fixture",
  );
  expect(options.redirect).toBe("manual");
  expect(options.headers.get("cookie")).toBe("binding-fixture=test");
  expect(options.headers.has("x-forwarded-for")).toBe(false);
  expect(response.headers.get("cache-control")).toContain("no-store");
});

test("proxy forwards CSRF and Origin and preserves a server-side rejection", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      Response.json({ error: { code: "CSRF_REJECTED" } }, { status: 403 }),
    );
  vi.stubGlobal("fetch", fetcher);
  const response = await POST(
    makeRequest("http://127.0.0.1:3100/api/v1/auth/logout", {
      method: "POST",
      headers: {
        Origin: "http://127.0.0.1:3100",
        "X-CSRF-Token": "fixture",
        Cookie: "fixture=opaque",
      },
    }),
    context("auth/logout"),
  );
  expect(response.status).toBe(403);
  expect(fetcher.mock.calls[0][1].headers.get("x-csrf-token")).toBe("fixture");
  expect(fetcher.mock.calls[0][1].headers.get("origin")).toBe(
    "http://127.0.0.1:3100",
  );
});

test("unavailable backend, unsafe redirects and internal origins never leak details", async () => {
  const request = makeRequest(
    "http://127.0.0.1:3100/api/v1/auth/steam/callback",
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(null, {
        status: 303,
        headers: { Location: "http://api:8000/account" },
      }),
    ),
  );
  expect(
    (await GET(request, context("auth/steam/callback"))).headers.get(
      "location",
    ),
  ).toBe("http://127.0.0.1:3100/login?error=LOGIN_FAILED");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error("SECRET_COOKIE_AND_PASSWORD")),
  );
  const response = await GET(
    makeRequest("http://127.0.0.1:3100/api/v1/me"),
    context("me"),
  );
  expect(response.status).toBe(502);
  expect(await response.text()).not.toContain("SECRET_COOKIE_AND_PASSWORD");
});

test("proxy rejects arbitrary destinations, noncanonical origin and oversized writes", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  expect(
    (
      await GET(
        makeRequest("http://127.0.0.1:3100/api/v1/unknown"),
        context("unknown"),
      )
    ).status,
  ).toBe(404);
  expect(
    (await GET(makeRequest("http://localhost:3100/api/v1/me"), context("me")))
      .status,
  ).toBe(400);
  expect(
    (
      await POST(
        makeRequest("http://127.0.0.1:3100/api/v1/auth/logout", {
          method: "POST",
          body: "a".repeat(17000),
        }),
        context("auth/logout"),
      )
    ).status,
  ).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});

test("internal listener origin is not confused with browser Host", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: "fixture" }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    makeRequest("http://localhost:3200/api/v1/me", {
      headers: {
        Host: "127.0.0.1:3100",
        "X-Forwarded-Host": "attacker.invalid",
      },
    }),
    context("me"),
  );
  expect(response.status).toBe(200);
  const rejected = await GET(
    makeRequest("http://127.0.0.1:3100/api/v1/me", {
      headers: {
        Host: "attacker.invalid",
        "X-Forwarded-Host": "127.0.0.1:3100",
      },
    }),
    context("me"),
  );
  expect(rejected.status).toBe(400);
});
