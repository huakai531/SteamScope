import { isReadiness } from "@/lib/api/status";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    // Only the fixed health path is forwarded. No arbitrary proxy URL or browser secrets.
    const origin = new URL(
      process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8100",
    );
    if (
      !["http:", "https:"].includes(origin.protocol) ||
      origin.username ||
      origin.password ||
      origin.pathname !== "/" ||
      origin.search ||
      origin.hash
    )
      throw new Error("Invalid internal origin");
    const response = await fetch(new URL("/health/ready", origin), {
      cache: "no-store",
      signal: AbortSignal.timeout(3500),
    });
    const payload: unknown = await response.json();
    if (![200, 503].includes(response.status) || !isReadiness(payload))
      throw new Error("Invalid health response");
    return Response.json(payload, {
      status: payload.status === "ready" ? 200 : 503,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "STATUS_UNAVAILABLE",
          message: "Cannot reach the foundation API",
        },
      },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
