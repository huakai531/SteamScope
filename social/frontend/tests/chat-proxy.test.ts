import { afterEach, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

afterEach(() => vi.unstubAllEnvs());

function request(overrides: Record<string, string> = {}, query = "") {
  return new NextRequest("http://127.0.0.1:3100/api/v1/ws" + query, {
    headers: {
      host: "127.0.0.1:3100",
      origin: "http://127.0.0.1:3100",
      upgrade: "websocket",
      ...overrides,
    },
  });
}

test("socket proxy uses the runtime private upstream and rejects cross-site upgrades", () => {
  vi.stubEnv("INTERNAL_API_URL", "http://api:8000");
  const response = proxy(request());
  expect(response.headers.get("x-middleware-rewrite")).toBe(
    "http://api:8000/api/v1/ws",
  );
  const rejected: Record<string, string>[] = [
    { origin: "https://untrusted.invalid" },
    { host: "untrusted.invalid" },
    { origin: "null" },
  ];
  for (const headers of rejected)
    expect(proxy(request(headers)).headers.get("x-middleware-rewrite")).toBe(
      "http://api:8000/api/v1/ws?rejected=1",
    );
  expect(
    proxy(request({}, "?credential=synthetic")).headers.get(
      "x-middleware-rewrite",
    ),
  ).toBe("http://api:8000/api/v1/ws?rejected=1");
  expect(proxy(request({ upgrade: "http" })).status).toBe(403);
});

test("socket proxy rejects credentials paths and unsupported upstream protocols", () => {
  for (const upstream of [
    "http://synthetic:synthetic@api:8000",
    "http://api:8000/private",
    "http://api:8000/?route=override",
    "file:///api",
  ]) {
    vi.stubEnv("INTERNAL_API_URL", upstream);
    expect(proxy(request()).status).toBe(503);
  }
});
