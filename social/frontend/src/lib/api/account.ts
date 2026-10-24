import type { components } from "./schema";

export type Account = components["schemas"]["AccountView"];
export type Privacy = components["schemas"]["PrivacyView"];
export type Session = components["schemas"]["SessionView"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];
export type APIError = components["schemas"]["ErrorResponse"];

export class AccountError extends Error {
  constructor(
    public status: number,
    public detail: APIError["error"],
  ) {
    super(detail.code);
  }
}

export async function accountRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") {
    const csrf =
      await accountRequest<components["schemas"]["CSRFView"]>("/auth/csrf");
    headers["X-CSRF-Token"] = csrf.csrf_token;
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/v1" + path, {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    if (
      response.status === 401 &&
      !(method === "GET" && path === "/me") &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("steamscope-auth-ended"));
    const payload = (await response.json()) as APIError;
    throw new AccountError(
      response.status,
      payload.error ?? { code: "UNAVAILABLE", message: "Request unavailable" },
    );
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function accountMessage(error: unknown): string {
  if (!(error instanceof AccountError))
    return "Cannot reach your account. Please try again.";
  const messages: Record<string, string> = {
    AUTH_REQUIRED: "Your session has ended. Sign in again.",
    HANDLE_UNAVAILABLE: "That handle is already in use. Choose another.",
    INVALID_REQUEST: "Check the highlighted fields and try again.",
    RATE_LIMITED:
      "Too many requests. Please wait a minute before trying again.",
    REAUTH_REQUIRED:
      "Verify your Steam identity again before deleting your account.",
    CSRF_REJECTED:
      "Your session changed. Reload this page before trying again.",
    ORIGIN_REJECTED:
      "Open SteamScope at its configured browser address and try again.",
  };
  return (
    messages[error.detail.code] ??
    "The request could not be completed. Please try again."
  );
}
