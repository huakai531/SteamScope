const routes: Record<string, string[]> = {
  "auth/steam/login": ["GET"],
  "auth/steam/callback": ["GET"],
  "auth/steam/reauth": ["POST"],
  "auth/csrf": ["GET"],
  "auth/logout": ["POST"],
  "auth/logout-all": ["POST"],
  me: ["GET", "PATCH", "DELETE"],
  "me/avatar": ["POST", "DELETE"],
  "me/privacy": ["GET", "PATCH"],
  "me/sessions": ["GET"],
  "me/steam/sync": ["POST"],
  "me/steam/sync-status": ["GET"],
  "me/steam/profile": ["GET"],
  "me/steam/games": ["GET"],
  "me/steam/recent-games": ["GET"],
  "me/steam/data": ["DELETE"],
  "me/steam/friends": ["GET"],
  "me/steam/friends/sync": ["POST"],
  "users/search": ["GET"],
  "discovery/players": ["GET"],
  "discovery/steam-friends": ["GET"],
  "connection-requests": ["POST"],
  "connection-requests/incoming": ["GET"],
  "connection-requests/outgoing": ["GET"],
  connections: ["GET"],
  blocks: ["GET"],
  reports: ["POST"],
  notifications: ["GET"],
  "notifications/read-all": ["POST"],
  "conversations/direct": ["POST"],
  conversations: ["GET"],
};

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

function unavailable(code: string, status: number) {
  return Response.json(
    { error: { code, message: "Account request could not be completed" } },
    {
      status,
      headers: {
        "Cache-Control": "no-store, private",
        "Referrer-Policy": "no-referrer",
      },
    },
  );
}

async function bodyWithinLimit(
  request: Request,
  limit: number,
): Promise<ArrayBuffer | undefined> {
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.length;
    if (length > limit) {
      await reader.cancel();
      throw new Error("body-limit");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return bytes.buffer;
}

async function proxy(request: Request, context: Context) {
  const { path } = await context.params;
  const route = path.join("/");
  const chatMethods = /^conversations\/[0-9a-f-]{36}\/messages$/i.test(route)
    ? ["GET", "POST"]
    : /^conversations\/[0-9a-f-]{36}\/read$/i.test(route)
      ? ["POST"]
      : /^conversations\/[0-9a-f-]{36}$/i.test(route)
        ? ["GET"]
        : /^messages\/[0-9a-f-]{36}\/report$/i.test(route)
          ? ["POST"]
          : /^messages\/[0-9a-f-]{36}$/i.test(route)
            ? ["DELETE"]
            : undefined;
  const methods =
    (/^users\/[A-Za-z][A-Za-z0-9_]{2,23}\/avatar\/[a-f0-9]{32}\.webp$/.test(
      route,
    )
      ? ["GET"]
      : undefined) ??
    chatMethods ??
    (/^connection-requests\/[0-9a-f-]{36}\/(accept|reject)$/i.test(route)
      ? ["POST"]
      : /^connection-requests\/[0-9a-f-]{36}$/i.test(route)
        ? ["DELETE"]
        : /^notifications\/[0-9a-f-]{36}\/read$/i.test(route)
          ? ["POST"]
          : /^connections\/[A-Za-z][A-Za-z0-9_]{2,23}$/.test(route)
            ? ["DELETE"]
            : /^blocks\/[A-Za-z][A-Za-z0-9_]{2,23}$/.test(route)
              ? ["POST", "DELETE"]
              : /^users\/[A-Za-z][A-Za-z0-9_]{2,23}(?:\/games(?:\/[1-9][0-9]{0,9}(?:\/achievements)?)?|\/comparison|\/relationship)?$/.test(
                    route,
                  )
                ? ["GET"]
                : /^me\/sessions\/[0-9a-f-]{36}$/i.test(route)
                  ? ["DELETE"]
                  : /^me\/steam\/sync-jobs\/[0-9a-f-]{36}$/i.test(route)
                    ? ["GET"]
                    : /^me\/steam\/games\/[1-9][0-9]{0,9}\/achievements$/.test(
                          route,
                        )
                      ? ["GET"]
                      : /^me\/steam\/games\/[1-9][0-9]{0,9}\/achievements\/sync$/.test(
                            route,
                          )
                        ? ["POST"]
                        : routes[route]);
  if (!methods?.includes(request.method))
    return unavailable("ROUTE_NOT_FOUND", 404);
  const incoming = new URL(request.url);
  const browserOrigin = process.env.BROWSER_ORIGIN ?? "http://127.0.0.1:3100";
  // Next reconstructs request.url with its internal listener origin. Only compare
  // the received Host with the configured allowlist; never derive redirects from it.
  if (request.headers.get("host") !== new URL(browserOrigin).host)
    return unavailable("CANONICAL_ORIGIN_REQUIRED", 400);
  if (incoming.search.length > 8192) return unavailable("INVALID_REQUEST", 400);
  const avatarUpload = route === "me/avatar" && request.method === "POST";
  const limit = avatarUpload ? 5 * 1024 * 1024 : 16384;
  const length = request.headers.get("content-length");
  if (length && (!/^\d{1,10}$/.test(length) || Number(length) > limit))
    return unavailable(
      avatarUpload ? "AVATAR_TOO_LARGE" : "BODY_TOO_LARGE",
      413,
    );
  if (avatarUpload && request.headers.get("origin") !== browserOrigin)
    return unavailable("ORIGIN_REJECTED", 403);
  if (
    avatarUpload &&
    (!["image/png", "image/jpeg", "image/webp"].includes(
      request.headers.get("content-type") ?? "",
    ) ||
      request.headers.has("content-encoding"))
  )
    return unavailable("AVATAR_FORMAT_UNSUPPORTED", 415);
  try {
    const internal = new URL(
      process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8100",
    );
    if (
      !["http:", "https:"].includes(internal.protocol) ||
      internal.username ||
      internal.password ||
      internal.pathname !== "/" ||
      internal.search ||
      internal.hash
    )
      throw new Error("configuration");
    const headers = new Headers();
    for (const key of [
      "cookie",
      "origin",
      "content-type",
      "x-csrf-token",
      "sec-fetch-site",
    ]) {
      const value = request.headers.get(key);
      if (value) headers.set(key, value);
    }
    const body = ["GET", "HEAD"].includes(request.method)
      ? undefined
      : await bodyWithinLimit(request, limit);
    const upstream = await fetch(
      new URL(`/api/v1/${route}${incoming.search}`, internal),
      {
        method: request.method,
        headers,
        body,
        redirect: "manual",
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
      },
    );
    const outgoing = new Headers({
      "Cache-Control": "no-store, private",
      Pragma: "no-cache",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of [
      "content-type",
      "retry-after",
      "x-request-id",
      "cross-origin-resource-policy",
      "content-security-policy",
    ]) {
      const value = upstream.headers.get(key);
      if (value) outgoing.set(key, value);
    }
    // Never join Set-Cookie: the callback sets a session and clears its binding cookie.
    for (const cookie of upstream.headers.getSetCookie())
      outgoing.append("Set-Cookie", cookie);
    const location = upstream.headers.get("location");
    if (location) {
      const redirect = new URL(location);
      const steam =
        redirect.origin === "https://steamcommunity.com" &&
        redirect.pathname === "/openid/login";
      const local =
        redirect.origin === browserOrigin &&
        /^\/(account(?:\/(profile|privacy|sessions|delete|steam))?|login)$/.test(
          redirect.pathname,
        );
      if (
        (!steam && !local) ||
        redirect.username ||
        redirect.password ||
        redirect.hash
      )
        throw new Error("redirect");
      outgoing.set("Location", location);
    }
    return new Response(
      upstream.status === 204 ? null : await upstream.arrayBuffer(),
      { status: upstream.status, headers: outgoing },
    );
  } catch (error) {
    if (error instanceof Error && error.message === "body-limit")
      return unavailable(
        avatarUpload ? "AVATAR_TOO_LARGE" : "BODY_TOO_LARGE",
        413,
      );
    // No request URL, assertion, cookie, credential or internal exception logging.
    if (route === "auth/steam/callback") {
      return new Response(null, {
        status: 303,
        headers: {
          Location: browserOrigin + "/login?error=LOGIN_FAILED",
          "Cache-Control": "no-store",
          "Referrer-Policy": "no-referrer",
        },
      });
    }
    return unavailable("ACCOUNT_API_UNAVAILABLE", 502);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
