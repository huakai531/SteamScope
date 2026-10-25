# Privacy model — implemented Phase 2 and future boundaries

OpenID proves a Steam identity; it grants no permission to fetch private Steam data.
Phase 2 stores platform profile, verified Steam linkage, privacy preferences, session digests,
short-lived login transactions and minimal audit events. Phase 3A additionally imports the linked owner’s Steam persona, visible library/playtime and recent activity only after an explicit request. Phase 3B adds explicit selected-game achievements and owner-requested Steam friend edges. No IP history, device fingerprint, chat or raw response collection.

| Preference | Implemented initial default | Current effect |
|---|---|---|
| Profile/library/playtime/achievements/presence | private | Persisted; settings remain owner-only |
| Discovery | false | Saved future preference; no discovery endpoint |
| Connection requests | nobody | Saved future preference; no connection endpoint |
| Messaging | nobody | Saved future preference; no messaging endpoint |

Broader choices require an explicit save. Identity fields/status cannot be mass-assigned.
The tested can_view policy requires active account and available source; only owner or public
visibility succeeds. Connections-only never grants stranger access in the absence of a
relationship system. Existing account routes always derive the owner from the session.

Future profiles, mutual games, aggregate counts, recommendations, presence and notifications
must intersect source availability, saved settings, real accepted relationship facts, block
policy and freshness. Caches must be actor/policy-scoped or reauthorize on read. These are
future requirements, not current implemented features. Never import Steam friends into
registered accounts or infer a public library from a public Steam summary.

Private responses are no-store. Browser caches clear on session end; no bearer credential or
private query persistence is stored in localStorage. See ADRs 0019–0021 and the deletion policy.
Data export and production privacy/legal review remain later work.

## Phase 3A owner-only source data

All new reads require the current session owner, regardless of saved public/connection settings.
Steam summary visibility never proves library or recent visibility. Unknown/denied resource states
hide old rows, counts, aggregates and page cursors server-side; explicit profile restriction erases
imported persona metadata. An exposure flag ensures later timeouts cannot reopen hidden data.
Source values are plain data, never code, glob patterns, commands or paths. No external image fetch
or raw payload retention exists. See [resource policy](../architecture/STEAM_DATA_FLOW.md).

Data is stored in the project owner's local PostgreSQL volume on their machine. No cloud copy is
created by Phase 3A. Any later deployment must explicitly identify its storage country/region in
the privacy notice before collecting data from other users; no location is inferred from timezone.

## Phase 3B: personal achievements and imported Steam edges

New reads are strictly session-owner-only even when saved future visibility settings say public.
Selected-game eligibility requires an exposed imported-library snapshot and owner/app row; this is
an access rule, not an entitlement claim. API names, descriptions and friend identifiers are bounded
data passed through parameterized SQL and escaped React text, never patterns, scripts or paths.
Friends create neither accounts nor platform relationships; no reverse lookup, enrichment or crawl.

Complete validated friends snapshots alone reconcile removals. Unknown/access-denied results hide
retained rows/counts/cursors; a later timeout cannot re-expose them. Friends expire from read visibility
after 900 seconds. Steam documents private friend-list HTTP 401; the implementation preserves
private-or-unauthorized uncertainty rather than asserting a globally invalid key. Achievement denial
hides personal values; stale permitted progress remains labelled with its previous timestamp and
without an exact completion percentage. Shared definitions contain no player's unlocks or friends.

Hidden achievement titles/descriptions are concealed by default with an owner reveal checkbox.
Validated icon URLs are stored, not fetched/proxied. Browser query keys include owner and scope/app;
clear/logout and cross-tab session handling erase all `steam` queries. No persistent browser cache.
No new external access or storage location was introduced; production remains unapproved.

### Verified Phase 3B source-privacy transition (2026-10-22)

USER VERIFIED: the selected game was not individually marked Private; Steam Game details was
Friends Only. The owner changed Game details to Public and requested new achievement syncs.
SERVER VERIFIED: the historical personal request remains HTTP 403 / PROFILE_NOT_PUBLIC, with
unknown/unavailable progress and no fabricated 0%; shared schema was accessible independently.
New personal requests returned HTTP 200 / success=true and persisted complete, matched progress.
This verifies compliance with Steam's source visibility, not a privacy bypass. The settings values
and their change were observed by the owner, not read automatically by SteamScope. This account/game
observation does not assert that every Steam 403 has the same cause or require all profiles public.

See [Phase 3B final evidence](../development/VALIDATION.md). User-confirmed empty friends plus a
validated empty snapshot is a successful empty path, not an error or a requirement to add friends.

## Phase 3C integrated privacy acceptance

Current real data is read-only evidence; no owner privacy toggle or new Steam request was needed.
New real-PG fixtures verify library ambiguous availability, personal 403 and friend 401 separately:
retained old rows and last success do not imply current permission; corresponding rows/counts/cursors
are hidden together, schema may remain shared, no false zero/completion is generated. A later valid
complete snapshot restores visibility with no duplicate rows; historical denial runs stay unchanged.
The new partial-response guard also hides existing personal progress while retaining accepted data.
Real Friends Only→Public settings remain USER VERIFIED, with historical and current server evidence
kept separate. Local acceptance grants neither public visibility nor deployment approval.

## Phase 4 effective player authorization (supersedes future-player text above)

The `/me` APIs remain owner-only. New `/users/{handle}` APIs require login and apply profile +
independent library/playtime/achievement settings server-side before any row/filter/count/sum.
`public` shares with signed-in viewers only; anonymous401. Private/connections profile404;
connections resources are owner-only. Imported Steam friend edges grant no access. Locale/timezone
remain owner-only. Non-owner stale/source-hidden snapshots fail closed; permitted owner historical
data is labelled, stale recent is hidden, exact stale completion is null.

See [explicit matrix and consistency semantics](../architecture/PLAYER_VIEWS.md). No cached
comparison or policy persists; next read reflects privacy/clear/delete changes. No hidden library
or achievement count, match evidence or cursor leaks. UI uses no-store requests and transient
query state, refetches on focus, clears on session end and does not contact Steam when viewing.

## Phase 5 current policy (supersedes Phase4 connections restriction)

Accepted SteamScope connections now grant `connections` resources through the shared policy;
imported Steam friendships never do. Either-side block denies both profiles and dependent views,
removes platform connections, cancels pending requests and removes pair notifications. Unblock
does not restore prior consent. Private remains owner-only. Source visibility/freshness are unchanged.
Discovery opt-in is now enforced before scoring/search. Locale/timezone are not matching signals.

[Current authorization matrix](../architecture/PLAYER_VIEWS.md) and
[specific invitation/relationship identity exceptions](../architecture/SOCIAL_GRAPH.md).
Reports remain private moderation evidence; no target-facing notification or reporter disclosure.
No external calls on reads, no untrusted input flowing to build tools or glob/brace matching.

## Phase 6 chat authorization matrix

| Current caller/relationship | List/history | Create/send | Typing/presence |
|---|---|---|---|
| Valid participant + active connection + both message settings allow | Yes | Yes | Typing yes; presence requires peer public/connections |
| Valid participant, disconnected or either messaging=nobody | History yes | No | No / unavailable |
| Either-direction block | Hidden/404 | No | No |
| Stranger/anonymous/expired/revoked/deleted | No | No | No |

Every outgoing event checks the same DB policy, including unrelated conversation hints. Private
peer profile yields no person projection; private presence is unavailable, never offline-as-a-leak.
No imported Steam friend grants authority. Existing sockets check current session/policy each second
with a tested8s operational revocation target; in-flight packets are not retractable. Current
chat/session data are cleared on unavailable/logout; auth restoration rechecks server state.
See DIRECT_CHAT for limits and read-history exception after voluntary connection removal.

## Platform avatar and game visuals

Uploaded SteamScope avatars follow profile visibility, including connections-only,
private and both-direction blocks. Each image read rechecks current authorization
and active key; opaque filenames alone are not authorization. Responses are private
and not cached. Directed request/notification consent does not grant profile-avatar
access. No public upload directory or image optimizer cache is exposed.

Game icons are included only in already-authorized game projections. The browser
may fetch the public Steam media CDN image (IP/AppID visible to that CDN), with
no referrer and no SteamScope cookies, API key or Steam account identity. Shared
game artwork cannot be used to query another user's library. See
[GAME_VISUALS](../architecture/GAME_VISUALS.md) and [AVATAR_STORAGE](AVATAR_STORAGE.md).
