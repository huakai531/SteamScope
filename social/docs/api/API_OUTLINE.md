# Implemented API contract — Phase 4

Canonical browser origin http://127.0.0.1:3100; browser API proxy /api/v1/*.
The native/container API uses the same paths. Fixed-origin proxy behavior is in ADR 0020.
OpenAPI JSON is exported by python -m steamscope_social.export_openapi; npm run api:types
generates src/lib/api/schema.d.ts. Do not maintain handwritten DTO duplicates.

| Method / route | Success | Authorization / behavior |
|---|---|---|
| GET /health/live | 200 alive | No dependencies |
| GET /health/ready | 200 ready / 503 unavailable | PostgreSQL/Redis probes; foundation scope, not a schema/live-login claim |
| GET /api/v1/system | 200 version 0.4.0, phase 4, subphase 4 | Public implemented-phase metadata |
| GET frontend /api/status | 200 / 503 readiness; 502 proxy unavailable | Fixed upstream, no-store |
| GET /api/v1/auth/steam/login | 303 official Steam URL | Browser-bound attempt, safe next allowlist, rate limit |
| GET /api/v1/auth/steam/callback | 303 clean account/login URL | One-time attempt + complete OpenID verification + nonce |
| POST /api/v1/auth/steam/reauth | 200 {url} + binding cookie | Session, CSRF, Origin; must return same Steam identity |
| GET /api/v1/auth/csrf | 200 {csrf_token} | Authenticated, memory-only uncached token |
| GET /api/v1/me | 200 AccountView | Current session owner only |
| PATCH /api/v1/me | 200 AccountView | CSRF/Origin; only handle/display_name/biography/locale/timezone |
| GET /api/v1/me/privacy | 200 PrivacyView | Owner only |
| PATCH /api/v1/me/privacy | 200 PrivacyView | Partial allowlisted settings; CSRF/Origin |
| GET /api/v1/me/sessions | 200 SessionView[] | At most 20 active owned sessions; no token/digest/IP |
| DELETE /api/v1/me/sessions/{session_id} | 204 | Owner-scoped UUID; CSRF/Origin; clear cookie if current |
| POST /api/v1/auth/logout | 204 | Revoke current credential + bound attempts; clear cookie |
| POST /api/v1/auth/logout-all | 204 | Revoke all credentials + account-bound attempts |
| DELETE /api/v1/me | 204 | CSRF/Origin, {confirmation:"DELETE"}, recent identity; atomic erasure |
| POST /api/v1/me/steam/sync | 202 new / 200 reused | Session-derived owner/link; CSRF/Origin; active dedup; 429 cooldown; 503 unconfigured |
| GET /api/v1/me/steam/sync-status | 200 | Safe capability, independent resource attempt/success/freshness and latest job |
| GET /api/v1/me/steam/sync-jobs/{job_id} | 200 / 404 | Owned job and safe run history only |
| GET /api/v1/me/steam/profile | 200 | Owner-only imported Steam persona, separate from platform profile |
| GET /api/v1/me/steam/games | 200 / 409 | Bounded app-ID keyset pagination; after/limit/snapshot; hidden data suppresses totals/cursors |
| GET /api/v1/me/steam/recent-games | 200 | Captured two-week resource; no double counting; expires from read visibility after 15 minutes |
| DELETE /api/v1/me/steam/data | 204 | CSRF/Origin/recent identity + confirmation="CLEAR STEAM DATA"; generation fencing, no account deletion |

All authenticated routes derive the actor from a cookie, never a caller-supplied user_id.
SteamID64 and UUID are JSON/TypeScript strings. AccountView steam_data_synchronized is true only when all three resources have permitted, successful, fresh snapshots; per-resource endpoints remain authoritative.
SessionCookie and mandatory write Origin/X-CSRF-Token headers are described in OpenAPI.
Normal logout/deletion is not accomplished by merely clearing the browser cookie.

Safe error envelope: {error:{code,message,fields?},request_id?}. 401 missing/expired/revoked;
403 Origin/CSRF/recent-auth/status; 404 unowned session; 409 case-insensitive handle conflict;
422 invalid/unknown/server-controlled fields; 429 shared Redis rate limit; 503 dependency
unavailable. Proxy can return 400 wrong canonical host, 404 nonallowlisted route/method,
502 upstream/size/redirect failure. Callback failures redirect to safe constant login codes.
Errors never echo raw input, credentials, SQL or assertion payloads. Unexpected 500 remains
sanitized. All account responses use private/no-store and no-referrer.

Profile: handle ASCII letter then letters/digits/underscore, 3–24; display name 1–60;
plain-text bio up to 500; supported locales en/en-US/zh-CN/zh-TW/ja/ko/de/fr/es/pt-BR;
IANA timezone up to 64 validated with tzdata. HTML is rendered as text. See generated schemas.

Login/callback: 10 per API peer per 300s each. Sensitive writes: 30/account/60s by default.
The local same-origin proxy shares a peer quota. Outages never authenticate without checks.
The current read-only session check needs PostgreSQL; writes and login additionally need Redis.

Future endpoints (not implemented): public profiles/comparisons (P4),
discovery/connections/blocks/reports (P5), chat/WebSockets (P6). No placeholder domain APIs.

## Phase 3B owner-only additions

| Method / route | Behavior |
|---|---|
| POST /api/v1/me/steam/games/{appid}/achievements/sync | CSRF/Origin; verified owner identity; eligible visible imported game; 202 new / 200 active reuse; 429 per-app cooldown/owner queue cap/shared quota |
| GET /api/v1/me/steam/games/{appid}/achievements | Saved personal state + English shared definitions; app range 1..2^32-1; 404 ineligible; limit 1..100 default 50; after API name + snapshot UUID + revision; 409 changed snapshot |
| POST /api/v1/me/steam/friends/sync | CSRF/Origin; explicit owner's friend-list job only; 202/200/429/503 as above |
| GET /api/v1/me/steam/friends | Saved owner list only; limit 1..100 default 25; after SteamID64 string + snapshot UUID; 409 changed snapshot |

Existing `/sync-jobs/{job_id}` supplies owner-only task/run detail. Job DTO adds scope/app_id.
Base `/sync-status` and AccountView's base-sync flag continue to concern profile/library/recent only.
No GET contacts Steam or creates jobs. No caller-supplied identity, public friend route or enrichment.
All four routes use the existing fixed proxy allowlist and private/no-store session contract.

Achievements expose independent state/schema_state, latest_job, coverage (unknown/complete/partial/
no_achievements/stale), known counts, definition_count and nullable completion_percent. Missing player
state is null, never implicitly locked; zero unlocktime maps to null. Shared definitions can still be
shown without private progress. Friends hide rows, total_count and cursor together after denied/unknown
source evidence or 15-minute expiry; endpoint-specific 401 code is FRIENDS_PRIVATE_OR_UNAUTHORIZED.
Generated OpenAPI and TypeScript types, not this summary, define exact fields.

Real Phase 3B acceptance (2026-10-22) verified a shared schema success alongside a personal
HTTP 403 / PROFILE_NOT_PUBLIC, followed by personal HTTP 200 / success=true after the owner
changed Game details from Friends Only to Public (settings are USER VERIFIED). Historical denial
jobs retain their results; new validated snapshots update personal state and last_success_at.
Completion is computed from matching complete schema/player identifiers and known boolean states,
with freshness checks, rather than a stored percentage or treating unknown as locked. This is an
observed source-privacy transition, not an API guarantee that all 403 responses mean privacy.

## Phase 3C acceptance of the existing contract

No routes or DTOs changed; exported OpenAPI and generated TypeScript remain identical. A new
SCHEMA_PLAYER_MISMATCH observation over an existing snapshot uses the existing unknown status:
data_available=false, personal known counts/completion null, definition-only unknown items, and
previous last_success_at preserved. It does not turn absent achievement values into locked.
Known partial counts describe only observed rows; exact completion still requires compatible
complete fresh coverage. New complete data restores visibility without changing old task history.

Owner authorization, no-store, deterministic keyset pagination/snapshot rejection, resource/app/task
feedback binding, refresh, clear/logout cache removal and no GET-triggered Steam calls were checked
with the complete local suite. See [Phase 3 final acceptance](../development/VALIDATION.md).

## Phase 4 session-authorized player API

| GET route | Response |
|---|---|
| /api/v1/users/{handle} | PlayerProfile: separate identities, authorized summaries, independent source state |
| /api/v1/users/{handle}/games | PlayerLibrary: q (0..80), sort name/total/recent/last_played, achievements/recent bool, cursor, limit |
| /api/v1/users/{handle}/games/{appid} | PlayerGameDetail: visible membership only |
| /api/v1/users/{handle}/games/{appid}/achievements | PlayerAchievements: permitted definitions/progress, cursor/limit |
| /api/v1/users/{handle}/comparison | PlayerComparison: session owner vs handle target; cursor/limit |

All require session credentials (anonymous401). Handle letters first, 3..24 ASCII letters/digits/_;
appid1..4294967295; limit1..100; cursor<=180. Private/missing/inactive/unlinked profiles404;
hidden/nonmember game404. Malformed input/unsupported privacy-sensitive filter422; changed visible
snapshot409. Standard ErrorResponse/no-store boundary applies. No viewer_user_id input is trusted.
Response count null means unavailable; zero means justified known empty. Other metadata is
suppressed with hidden resources. No GET creates jobs or calls Steam. Generated DTOs are authoritative.
See [player policy and route map](../architecture/PLAYER_VIEWS.md) for all authorization, snapshot,
source TTL and comparison semantics. The Phase 3 `/me/steam` owner-only contracts remain in place.

## Phase 5 social API

All routes below are prefixed `/api/v1`; the authenticated session determines the actor.
Writes retain exact-Origin/session CSRF, no-store and Redis fail-closed limits. Handles use the
existing 3..24 ASCII format; request/notification UUIDs are object references, never user IDs.

| Methods / routes | Purpose |
|---|---|
| GET /users/search?q=... | Literal handle/display-name search, 3..64 trimmed chars, at most 20, no cursor |
| GET /discovery/players; /discovery/steam-friends | At most 20 explainable matches from up to 60 authorized candidates |
| GET /users/{handle}/relationship | Self/none/incoming/outgoing/connected; can_request or pending request reference |
| POST /connection-requests | Body {handle}; idempotent pending send; reverse pending 409 |
| GET /connection-requests/incoming; /outgoing | Owner pending lists, 25/page, max newest 1000 |
| POST /connection-requests/{request_id}/accept; /reject | Receiver-only transition |
| DELETE /connection-requests/{request_id} | Sender-only cancel |
| GET /connections; DELETE /connections/{handle} | Owner accepted list / explicit removal |
| GET /blocks; POST or DELETE /blocks/{handle} | Owner block list / block / unblock |
| POST /reports | Body {handle,reason,description}; receipt only, no report-list route |
| GET /notifications | Owner events, 25/page, max newest 1000 |
| POST /notifications/{notification_id}/read; /notifications/read-all | Recipient-only persisted read state |

List cursors are viewer/context bound (max 180 chars); no full registry export exists.
Errors use generic SOCIAL_UNAVAILABLE404 for hidden/missing targets; 409 for explicit lifecycle
conflicts, 422 invalid bounds/self action, 429 limit, 503 unavailable limiter. Never disclose reverse
block cause or reporter identity. Generated OpenAPI and TypeScript DTOs are authoritative.
[Social policy](../architecture/SOCIAL_GRAPH.md) specifies privacy, exact rates and score meaning.

## Phase 6 implemented contract

Generated OpenAPI/TypeScript add POST /conversations/direct, GET /conversations,
GET /conversations/{conversation_id}, GET/POST /conversations/{conversation_id}/messages,
POST /conversations/{conversation_id}/read, DELETE /messages/{message_id},
POST /messages/{message_id}/report, all under /api/v1. Existing routes remain.
Writes use the existing cookie + exact Origin + CSRF contract; no client sender/user identity.
Histories accept bounded before/after integer cursors; conversation list accepts a UUID cursor.
Responses are private/no-store. Body-less deleted-message DTOs and generic unavailable errors
prevent ordinary APIs from exposing deleted or unauthorized content.

WS /api/v1/ws uses the existing HttpOnly cookie and exact Origin, no query parameters. The
[versioned WebSocket contract](../architecture/DIRECT_CHAT.md#websocket-contract-v1) supplements
OpenAPI, which does not model WebSockets. Redis hints never constitute successful persistence.
