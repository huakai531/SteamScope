# ADR 0020 — Sessions, CSRF and the same-origin proxy

Status: implemented; production deployment is outside this phase.

Canonical local browser origin: `http://127.0.0.1:3100`.
Callback: `http://127.0.0.1:3100/api/v1/auth/steam/callback` plus generated state.
Container-only API: `http://api:8000`; native API: `http://127.0.0.1:8100`.
Never mix localhost/127.0.0.1. API callback and redirect origins come only from Settings.
Next checks the received Host against the configured host allowlist, not its reconstructed
internal request.url origin. It never uses Host or forwarded headers to construct a callback.
Forwarded headers are stripped and Uvicorn proxy-header trust is disabled. Authentication
rate limits therefore share the frontend peer IP in Compose (conservative for a local demo);
a public multi-user proxy strategy is a future deployment decision, not an IP bypass here.

Sessions contain at least 256 random bits. Only SHA-256 digests persist. A fresh token is
issued after every authentication; a bound previous session is revoked. Defaults:
absolute 7 days, idle 1 day, recent-auth window 10 minutes, max 20 active sessions per user.
Settings/Compose expose the durations. Every account request verifies current account status,
revocation, absolute and idle expiry in PostgreSQL. User row locking serializes deletion,
revocation and authenticated updates; first login also locks the verified Steam identity and
uses uniqueness constraints plus nested transactions for handle collisions.

Cookie: HttpOnly, SameSite=Lax, Path=/, no Domain. Production requires HTTPS and Secure,
with name __Host-steamscope_session. Non-Secure steamscope_session is allowed only for
explicit development/test HTTP on 127.0.0.1. Per-attempt binding cookies are HttpOnly/Lax,
callback-path-scoped; secure deployments use __Secure-. Deletion uses matching cookie scope.
The proxy preserves each Set-Cookie separately and handles redirects manually.

Writes require the authenticated session, exact Origin, and a constant-time checked
session-bound HMAC CSRF value from the uncached GET /auth/csrf endpoint. The browser holds
it in request memory only. SameSite is supplemental. CORS has no credentialed wildcard;
account browser traffic uses the same-origin proxy. All account responses use no-store/private.
Proxy route/method/redirect allowlists, 8 KiB query and 16 KiB streamed body bounds reduce
exposure. Native API is an internal/loopback interface, not an alternate browser trust origin.

Redis Lua INCR/EXPIRE bounds initiation/callback at 10 each per 300s per API peer and
sensitive writes at 30 per 60s per account (configurable). Redis failure yields 503 or a
safe failed-login redirect. Existing read-only account access still depends on PostgreSQL.
No flush is used. Retry-After is a conservative 60s hint; login UI asks to wait five minutes.

Frontend queries never persist to localStorage. Full-document authentication navigation
starts a fresh cache; logout/deletion cancel and clear queries, broadcast session end to
other tabs and replace the URL. The sending tab reuses its channel to avoid consuming its
own notification. A 401 during a mutation clears the account view. Focus/mount revalidate;
bfcache restoration hides the old document and reloads before reuse.

Logging excludes access URLs, OpenID parameters, cookie values, raw exceptions and client
HTTP traces. Next request logging is disabled; API errors log only category/request UUID.
Future gateways must adopt the same rules. This phase has no external analytics/telemetry.

Sources: [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html),
[Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
Installed Next.js 16.4.2 route-handler, request/response and logging documentation was read.
