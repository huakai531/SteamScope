# Player views and authorization — Phase 5 policy extension

Player routes use existing verified SteamScope accounts only. Phase 5 reuses this projection
for discovery and extends its shared authorization with accepted platform connections and blocks.
The separate social API is documented in [SOCIAL_GRAPH](SOCIAL_GRAPH.md). No chat is implemented.

## Identity and audience

Canonical routes are mutable `/users/{handle}` (case-insensitive resolution, canonical handle in
DTO). Handles are not credentials. Session ownership is always the internal user UUID. A renamed
handle stops resolving; if later reused, it refers to that new account under its own privacy.
Old page cursors include hashed viewer and target UUID context and cannot transfer authorization.
No alias or permanent-ID route is created. Locale/timezone remain owner-only until separate consent.
Platform display name/handle/bio remain distinct from imported Steam persona and the validated
Steam profile link. Player DTOs contain neither raw SteamID nor internal UUID.

**Phase 4 requires authentication for every player API.** A `public` preference means shared with
other signed-in SteamScope users in this phase; anonymous requests return 401. It does not authorize
public deployment or anonymous browsing. Private, missing, inactive and unlinked profiles use the
same 404 PLAYER_NOT_AVAILABLE response. Hidden games use 404 PLAYER_GAME_NOT_AVAILABLE.

## Phase 4 baseline permissions (historical; Phase 5 extension below applies)

Profile preference gates access to platform identity and all dependent views. Per-resource
settings then intersect with source visibility and freshness. Steam profile visibility does not
prove library or achievement visibility; these sources are independent.

| Resource | Owner | Authenticated non-owner, public | Non-owner, private/connections | Anonymous |
|---|---|---|---|---|
| Platform profile | Active verified account | Profile public | 404 | 401 |
| Steam persona | Exposed current or permitted historical snapshot | Current exposed profile snapshot | Profile gate 404 | 401 |
| Library and game names/counts | Exposed current or permitted historical snapshot | Profile + library public, current exposed library | No rows/counts/cursor | 401 |
| Minutes, last played, recent filters | Visible library; recent expires | Visible library + playtime public | Null values, no ranking/filter evidence | 401 |
| Achievement definitions/progress/counts | Visible library + exposed personal snapshot; stale known state retained | Visible library + achievements public + fresh exposed player state | No definitions/progress/counts/percentages | 401 |
| Comparison | Session owner compared to authorized target | Intersection of authorized rows, never full hidden libraries | No hidden mutual evidence | 401 |

In Phase 4, `connections` was owner-only. The current Phase 5 matrix below supersedes that
restriction. Imported Steam friendship still grants no access. Discovery preferences are now
active; presence remains dormant. Settings are not changed by viewing a player.

Library TTL is 21600 seconds; profile/recent/player progress TTL is 900 seconds; English schema
TTL comes from the existing configured policy (default 86400 seconds). A retained exposed failure
is stale, even before age expiry. Restricted/unknown non-exposed snapshots remain hidden for the
owner too. Owner stale library/player data is historical only. Stale recent windows are hidden.
Known historical achievement counts and states are retained; exact completion is null until both
schema and personal data are fresh, revision-compatible, complete and boolean-known. Zero
applicable definitions is `no_achievements`, with no percentage. Partial observations never imply
all remaining achievements are locked. Source policy is based on last observed evidence and TTL;
viewing cannot detect an unobserved change on Steam, because GET never contacts Steam.

## Reads, pagination and comparison

After the existing credential validation/activity update, a separate PostgreSQL REPEATABLE READ,
READ ONLY transaction revalidates that session and reads a consistent policy/data snapshot. This
avoids holding target account locks and mixed privacy/data reads. Changes/revocation completed
before the snapshot apply immediately; an already-running overlapping read is evaluated at its
snapshot, not retroactively revoked. No cross-user results or authorization are stored in Redis,
localStorage, persisted query caches or summary tables.

Projection removes disallowed fields and rows **before** search, filtering, sorting, count and sum.
Library search is bounded literal casefold substring matching, not SQL LIKE, regex, glob or brace
expansion. Sort allowlist: name, total, recent, last_played; numeric/date unknowns last, appid breaks
ties. An unavailable sort/filter is rejected without looking at hidden values. Recent-only means a
known positive recent-minute value; explicit zero stays zero. Name search is within visible library,
not platform player search.

Pagination uses an opaque base64 encoded digest/offset cursor, bound to viewer/target UUID, filters,
visible projected rows and state. The digest contains no raw identity; it is not an authentication
token and need not be signed: every request reauthorizes and offset changes can only select already
visible rows. Changed context/data gives 409, malformed/bounded input 422. Restart from page one.
Limit 1..100; games/comparison defaults 25, achievements 50. Current implementation projects the
bounded imported library in memory (source cap 20,000), then pages; not a load-tested discovery API.

Comparison left side is always the session owner. Both sides are read in the same transaction.
Mutual membership is appid intersection after authorization. Unknown minutes propagate to totals
and differences; zero is returned only when justified by known values or a visible empty set.
Recent values are shown only when both are known/visible. Paired completion appears only when both
sides are complete/fresh and match the same current shared English schema. Independent coverage
still explains partial/stale/unavailable data. Summary counts cover the full visible intersection,
not just the current page; no score, ranking, or global Steam achievement completion is derived.

## Frontend routes

| Page | Read APIs | Purpose |
|---|---|---|
| /users/{handle} | GET /api/v1/users/{handle} | Identity, library summary, most played, accepted recent window |
| /users/{handle}/games | GET /api/v1/users/{handle}/games | Literal search, allowed filters/sorts, paging |
| /users/{handle}/games/{appid} | GET game + /achievements | Persisted minutes, saved known states and valid unlock times |
| /users/{handle}/compare | GET /api/v1/users/{handle}/comparison | Session owner vs existing authorized target |

Account navigation exposes `Player profile`; owner views link to the existing `Manage Steam data`.
`Reload saved data` only refetches GET. No sync button or new Steam write path is placed in player
views. React escapes text; links use validated backend Steam profile URLs; no untrusted HTML/image
proxy. Hidden achievement spoilers require an explicit reveal checkbox.

Query state has gcTime=0 and no persistence; requests and responses are private/no-store. Route and
filter keys isolate views; loading/refetch/error replaces prior data. Focus refetches; session-ended
broadcast/401 clears queries and hides content, bfcache restore reloads. Already-displayed data is
not claimed to disappear at the exact instant another tab changes privacy: the next read/focus or
Reload saved data enforces current policy, and historical browser observations cannot be revoked.

## Evidence boundaries

The five-account A/B/C/D/E integration fixture runs only in the guarded test database and normal
browser fixtures use a mocked upstream transport behind test-only process configuration. They are
excluded from production images, create no auth bypass endpoint, and are not real multi-user proof.
See the public validation summary for current counts and the separate real-owner manual check. No second genuine
account is required for local acceptance; public exposure and Phase 5 need separate authorization.

## Phase 5 current authorization matrix

The same `Access.permits` policy gates profile first, then library/playtime/achievements before
any filtering or aggregation. Source exposure/freshness and all existing Unknown/stale rules remain.

| Preference / viewer | Owner | Stranger | Accepted SteamScope connection | Either-side blocked | Anonymous |
|---|---|---|---|---|---|
| public | Allowed | Allowed | Allowed | Denied | 401 |
| connections | Allowed | Denied | Allowed | Denied | 401 |
| private | Allowed | Denied | Denied | Denied | 401 |

Denied profile is generic404; denied subordinate resources expose no rows/counts/cursor and null
minutes/completion. Imported Steam friends behave as strangers until explicit acceptance.
Search/discovery also require active verified/discoverable candidates. Locale/timezone remain
owner-only. Removing a connection/blocking/revoking privacy applies to the next authorized read.
Explicit owner relationship lists and pending sender introductions disclose only minimal platform
handle/name as documented in SOCIAL_GRAPH; they do not grant access to a now-private profile.
