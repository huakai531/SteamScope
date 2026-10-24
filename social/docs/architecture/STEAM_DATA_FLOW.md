# Phase 3A/3B Steam source mapping and snapshot policy

Official sources reviewed 2026-10-22:
[overview and service-interface format](https://partner.steamgames.com/doc/webapi_overview),
[Web API authentication](https://partner.steamgames.com/doc/webapi_overview/auth),
[ISteamUser](https://partner.steamgames.com/doc/webapi/ISteamUser),
[IPlayerService](https://partner.steamgames.com/doc/webapi/IPlayerService),
[terms](https://steamcommunity.com/dev/apiterms).

All requests use `https://api.steampowered.com`, certificate verification, no redirects, no
environment proxy trust and the `x-webapi-key` header. The partner host shown in some interface
reference examples is not used with this project's standard user key. The two service methods
use URL-encoded input_json; key/format remain outside that JSON. No publisher ownership method.

| Resource | Fixed endpoint | Parameters and normalized fields |
|---|---|---|
| Profile | ISteamUser/GetPlayerSummaries/v2 | One session-derived steamids string; exact returned identity; persona, validated avatar URL, canonical profile URL, visibility. No real name/location. |
| Library | IPlayerService/GetOwnedGames/v1 | input_json: steamid string, include_appinfo=true, include_played_free_games=true; no appids_filter. Unique app IDs, name/icon hash, integer total/recent minutes, optional actual last-played timestamp. |
| Recent | IPlayerService/GetRecentlyPlayedGames/v1 | input_json: steamid string, count=0 for all; separate recent rows and captured two-week window. Never add its lifetime minutes to the library total. |

Played free games are intentionally included. Returned game count is an observed API result,
not a purchase/DLC/entitlement inventory. Optional absent playtime is null, distinct from 0.
Steam persona never updates the SteamScope handle/display_name/biography. Names are bounded
plain strings, SQL parameters and escaped React text; they are never interpreted as glob patterns,
commands, paths, markup or build configuration. No store scraping, image download/proxy, app-detail
fan-out or third-party aggregator exists. The UI renders placeholders, not external images.

Each response is capped at 4 MiB and 20,000 unique valid apps. Connect timeout 3s, I/O timeout 5s,
whole resource timeout 10s. Booleans/numeric strings are rejected as numeric fields; app IDs are
1..2^32-1 and minutes 0..2^31-1. Missing optional fields are preserved as unknown. Extra harmless
fields are ignored and not stored. Malformed/duplicate entries or a mismatched count invalidate
the entire snapshot; no partially parsed library is reconciled. Raw responses are not persisted.

## Independent resource outcomes

| Outcome | Evidence | Persistence/read behavior |
|---|---|---|
| never | No saved resource attempt | No values or invented zero count |
| populated | All items valid, count matches; profile has matching identity and public visibility | Atomic complete snapshot replacement, new snapshot UUID and last_success_at |
| empty | Explicit game_count/total_count=0 with absent/empty games, no contradictory entries | Valid complete empty snapshot; removes previous associations for that resource |
| restricted | Profile explicitly reports visibility 1/2 | Erases imported profile metadata; does not infer library/recent visibility |
| unknown | Empty/missing count or inconclusive profile data | Retains previous rows but hides values/counts/aggregates/snapshot cursor on the server |
| unavailable | Endpoint's 401/403 without conclusive key/privacy evidence | Terminal access-denied code identifies resource, hides previous data; does not claim invalid key or private automatically |
| retry | 429, timeout/network, 5xx or application quota | Bounded delayed retries; previous permitted snapshot retained and marked stale |
| error/configuration | Invalid/mismatched/oversized response, other HTTP error, unavailable configuration | Terminal resource failure; no destructive reconciliation; general process health/login remain independent |

last_attempt_at is separate from last_success_at. Neither a retry nor a failure refreshes data age.
An exposed flag persists visibility evidence across later network failures: a timeout after an
unknown/denied response cannot accidentally re-expose retained old rows. Resource in_progress is
computed from active job outcomes without overwriting last known data/status.

Freshness budgets: profile/recent 15 minutes, library 6 hours. Profile/library owner-only snapshots
may remain visible after transient failure if no later hiding evidence occurred, with actual
last_success_at and stale=true. Recent entries and library two-week minutes are hidden after
15 minutes, so an old activity window cannot remain indefinitely current. Complete recent snapshots
remove absent entries. No timer silently syncs data; page polling only reads persisted results.

Read endpoints derive ownership from the existing session and always return private/no-store.
Library keyset pages order by app ID, limit 1..100 (default 25). Later pages supply the snapshot UUID;
replacement returns 409 so the caller restarts rather than mixing snapshots. Hidden data also hides
counts, totals and cursors. Shared catalog rows carry no user relationship after clear/delete.

## Retention

Successful imports remain until replacement, explicit clear, account deletion or explicit profile
restriction. Ambiguous/denied old library rows remain owner-linked but are hidden until a new
successful snapshot, clear or account deletion; they are not advertised as public/current. Recent
rows age out of read visibility at 15 minutes and are replaced/removed by a complete later snapshot.
Jobs retain at most 20 per owner on enqueue (including the new job); runs are bounded by attempts.
Clear retains only safe operational job outcomes/timestamps, no game names/playtime payloads.
Account deletion cascades jobs/runs and removes per-owner budget rows; shared nonpersonal budget
counters/catalog survive. No background retention scheduler is claimed.

## Phase 3B source mappings and independent coverage

Official methods and authentication reviewed 2026-10-22:
[ISteamUserStats](https://partner.steamgames.com/doc/webapi/ISteamUserStats),
[ISteamUser](https://partner.steamgames.com/doc/webapi/ISteamUser),
[authentication](https://partner.steamgames.com/doc/webapi_overview/auth).
Use the same public HTTPS host and private x-webapi-key header. These three interface methods use
normal query parameters (not IPlayerService's input_json). No unlock/reset/write methods are called.

| Resource | Method and parameters | Validated mapping |
|---|---|---|
| Shared schema | ISteamUserStats/GetSchemaForGame/v2; appid, l=english | game.availableGameStats.achievements[].name -> api_name; displayName, description, hidden, allowed HTTPS icon/icongray; sorted canonical definitions -> SHA-256 revision |
| Personal achievements | ISteamUserStats/GetPlayerAchievements/v1; steamid, appid, l=english | playerstats.success=true, achievements[].apiname -> api_name; explicit achieved 0/1 -> bool; missing -> null; unlocktime missing/0 -> null, valid known time -> UTC |
| Friends | ISteamUser/GetFriendList/v1; steamid, relationship=friend | friendslist.friends[].steamid string, relationship=friend, optional friend_since -> nullable UTC |

The official method pages specify endpoints/parameters and private-friends 401 behavior, but do not
fully enumerate these JSON response fields. `name` versus `apiname` and complete snapshot assumptions
are verified with deterministic boundary fixtures. Subsequent real 3B acceptance verified two
complete personal snapshots, a source-privacy denial/positive transition and a confirmed-empty
friend snapshot; user observations and read-only server evidence are separated in the public validation summary.
This does not claim real nonempty friends or every possible upstream payload. Missing arrays are unknown; explicit
validated arrays alone confirm empty. HTTP 200 application failures are not successful snapshots.

New lists are capped at 10,000 items and reuse the 4 MiB / bounded timeout policy. Duplicate IDs,
invalid types/ranges/identities, contradictory counts and unsupported partial friend pages cannot
destructively replace prior data. Source-provided identity/app IDs must match when present. Individual
SteamID64 range matches the already verified OpenID boundary (decimal string, not a narrow prefix).

Personal progress and schema may succeed/fail independently. Unknown IDs are saved and rendered as
missing definitions, with partial coverage. Added/removed definitions change the revision without
cascading personal rows. A later complete player snapshot can reset/remove unlocks; no monotonic rule.
Exact percentage uses all current unique definitions only when IDs, explicit booleans, revision and
freshness agree. Zero denominator produces no_achievements with null percentage, never 100%; unknown
player data is not zero. Known counts are shown separately and never labelled whole-library completion.

Schema TTL is an application default of 24h. Failed refresh preserves previous definitions but marks
the cache stale. Personal progress becomes stale at 15m; permitted stale rows can be shown with their
timestamp and no exact percentage. Friends hide both rows and count after denied/unknown evidence or
15m age. Complete new snapshots alone reconcile friend removals. Clear erases all personal 3B state
and scoped histories; shared definitions survive. See ADR 0023 for transaction/lease coordination.

## Phase 3C snapshot reconciliation clarification

An incomplete personal response cannot replace an existing saved snapshot: ID set, explicit
booleans and successful compatible schema must all agree before old personal rows are deleted.
On mismatch the attempt becomes unknown/SCHEMA_PLAYER_MISMATCH; prior rows/revision/success time
remain but are hidden. Malformed responses keep the existing error/stale policy. If there is no
old snapshot to erase, bounded first partial evidence retains its existing partial/known-count
semantics; it never yields exact completion. Later complete evidence can restore/reset progress.

The integrated readable→hidden→readable tests cover library, achievements and friends separately;
unknown library payload is not asserted private, and friend 401 remains private-or-unauthorized.
Current local acceptance and safe historical real snapshots are in the public validation summary; no new
Steam request was made for Phase 3C. Recent remains populated with one persisted record; a null
library recent_minutes is a different field, not proof of an empty recent resource.
