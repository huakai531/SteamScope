import { NextRequest, NextResponse } from "next/server";

// Next's upgrade handler resolves proxy rewrites before the dynamic REST route.
// Resolve at runtime so the same standalone build works in Docker and local tests.
export function proxy(request: NextRequest) {
  const origin = process.env.BROWSER_ORIGIN ?? "http://127.0.0.1:3100";
  const rejected =
    request.headers.get("host") !== new URL(origin).host ||
    request.headers.get("origin") !== origin ||
    !!request.nextUrl.search;
  if (request.headers.get("upgrade")?.toLowerCase() !== "websocket")
    return new NextResponse(null, { status: 403 });
  const upstream = new URL(
    process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8100",
  );
  if (
    !["http:", "https:"].includes(upstream.protocol) ||
    upstream.username ||
    upstream.password ||
    upstream.pathname !== "/" ||
    upstream.search ||
    upstream.hash
  )
    return new NextResponse(null, { status: 503 });
  // Next's raw Upgrade handler doesn't flush a middleware Response(403).
  // Route invalid upgrades to the API's unconditional query rejection instead.
  // Discard the supplied query entirely; no client credential is forwarded in it.
  return NextResponse.rewrite(
    new URL(rejected ? "/api/v1/ws?rejected=1" : "/api/v1/ws", upstream),
  );
}

export const config = { matcher: "/api/v1/ws" };
