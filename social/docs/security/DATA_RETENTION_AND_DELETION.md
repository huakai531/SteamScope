# Current retention and deletion policy

These are engineering behavior and defaults, not legal conclusions. Phase 2 has personal
account data; Phase 1 historical reports describe the earlier empty foundation.

| Current category | Retention / deletion |
|---|---|
| users profile/locale/timezone | Hard-deleted atomically on confirmed account deletion |
| steam_accounts | Verified association removed in the same transaction |
| privacy_settings | Same-transaction cascade deletion |
| user_sessions | Revocation denies next request; deletion erases digests immediately; cleanup removes expired/idle/revoked rows |
| login_attempts | 300-second validity; digest-only state/binding; consumed once; bound attempts cascade/revoke with account/session; cleanup removes expired rows |
| audit_logs | Event + time + event UUID + nullable actor only; actor is SET NULL on deletion; cleanup removes events older than 90 days |
| Redis nonce/rate keys | Hashed identifiers, namespace-scoped, TTL 60/300/660 seconds; no personal payload |

Deletion requires explicit DELETE confirmation, CSRF, exact Origin, active session and recent
verified Steam identity (default 600 seconds). POST /auth/steam/reauth starts a separate flow;
wrong identity fails. It may use an existing Steam session; no forced password/Steam Guard
claim is made. Deleting SteamScope does not change the owner's Steam account.

Atomic current-phase erasure means no profile/link/settings/session/bound-attempt row survives
if the transaction commits; failure rolls back the entire operation. Audit events are retained
without the user UUID or SteamID. Their event/time may still allow contextual correlation;
restrict database access. No user-facing audit browsing API is provided.

Executable maintenance, from social/:

```powershell
docker compose --env-file .env exec -T api python -m steamscope_social.modules.administration.cleanup
# Or with the intended environment already selected:
uv run --frozen --project backend python -m steamscope_social.modules.administration.cleanup
```

Run maintenance daily for the intended database. No scheduler is installed in this phase;
90 days is the deletion threshold, not a claim that unattended local containers purge on a
wall-clock deadline. Test execution invokes cleanup only against an isolated test database.
Before public release, schedule it and monitor failures. Never point tests at development data.

Fresh registration after deletion creates a new UUID and private defaults. Bound stale
callbacks and revoked credentials fail. Unlink is intentionally absent for a Steam-only account.

Phase 3A implements Steam snapshot/job generation fencing (see current section below).
Future integration obligations (not implemented):
connection/block cleanup; message content/attribution erasure with stable cursors; separately
restricted report evidence; socket/cache invalidation; notification expiry. Backups must have
bounded rotation and replay deletion decisions before restoration serves users. This phase
creates no backup policy implementation, export service, game or chat deletion endpoints.

## Phase 3A imported-data clearing and account deletion

DELETE /api/v1/me/steam/data requires exact CLEAR STEAM DATA confirmation, CSRF, Origin and recent
Steam verification. It preserves the login association, sessions and platform/private settings.
Under the same user lock used by final worker persistence it increments import_generation, erases
persona/library/recent/resource states, and cancels queued/running/retry jobs plus unfinished runs.
Old tokens/generations cannot publish after the clear; a fresh explicit request is required to
re-import. Safe job outcomes/timestamps and quota counters remain, without imported content.

Account deletion invokes the same fence, marks the user deleting, removes the per-user quota and
cascades imported associations/jobs/runs with the established account rows. Shared game metadata
and shared request counters retain no activity link to that user. No imported-data Redis cache
exists; HTTP is private/no-store and UI state resets on clear/logout, including cross-tab notices.
Tests pause a real client pipeline after the committed claim, clear/delete, then release the HTTP
response and prove that no data is resurrected. Tests never delete the owner's real account.

Snapshot visibility/retention, recent expiry and bounded histories are specified in
[STEAM_DATA_FLOW](../architecture/STEAM_DATA_FLOW.md); this section supersedes the old future-only
Steam erasure obligation. Future chat/connection/report retention remains unimplemented.

## Phase 3B extension of the same erasure transaction

Imported-data clear also deletes personal achievement rows/state and Steam friend edges/friend state.
It cancels/fences work under the same user lock and generation, releases schema leases belonging to
that owner's run tokens, then deletes non-base jobs/runs (selected app IDs are personal associations).
Base safe operational history and rate budgets remain as previously documented; account deletion
cascades all jobs/runs and removes per-user budget rows. Shared definitions/schema metadata and games
survive without personal progress/relationships. Another owner's imports remain intact.

Automated tests pause first schema HTTP, player-progress HTTP and friend HTTP, clear/delete, then
release results; old tokens cannot restore erased data. GET cannot recreate imports. Shared-schema
reuse by a second owner and snapshot resets/removals are covered. No real account deletion was used
for acceptance. Hidden older snapshots remain stored until valid replacement or explicit erasure;
this phase adds no unattended retention scheduler or public export.

## Phase 3C all-resource integration evidence

test_steam_acceptance runs clear and account deletion with populated profile/library/recent/player/
friend data, a blocked in-flight request and queued other scopes. User A's old response cannot write
after generation/account removal; A's six personal resource tables are empty, B's remain populated,
and shared game/schema survive. Clear retains verified login and local profile/settings; GET does
not re-import. Delete removes sessions/link/state/jobs, old credential reads return 401, and a new
registration gets a new UUID/default profile without resurrected imports. A new explicit sync is
required to import again. Existing first-schema and friend in-flight tests also ran in the full suite.
Only isolated fixture accounts were erased; all 18 development table digests and owner environment
files were unchanged. No owner deletion, backup claim or new retention scheduler is implied.

## Phase 5 actual graph and report deletion

Steam imported-data clear preserves platform requests/connections/blocks/reports/notifications;
it removes only Steam-derived recommendation evidence. Account deletion cascades requests,
connections, blocks and notifications (recipient or actor) with FKs, leaving no orphan graph.
Reports retain minimal moderation state for 90 days: deleted party FK becomes NULL and a database
BEFORE DELETE trigger clears the description whenever either party is deleted. Remaining party
reference/category/status/times are restricted, never included in public/player APIs.
Blocking/removing a connection does not destroy reports. Explicit administration cleanup removes
expired reports, notifications older than90days and terminal request history older than90days.
Cleanup is an explicit command, not an installed background schedule; operational scheduling is
required before any future deployment. Real PG tests separately cover clear, delete and both parties.

## Phase 6 direct-chat erasure and reports

Connection removal preserves history and disables new sends. Block hides access without deleting
history; unblock alone does not restore a connection. Own-message deletion persists a tombstone;
normal history/preview omit the body. Its one original body is eligible for blanking90days after
deleted_at through the existing explicit cleanup command. Reports reference it without copying text,
expire90days after creation, and cannot be edited by the reported sender. No unattended cleanup
scheduler is installed: operators must execute it; eligibility is not a physical-deletion guarantee.

Deleting either account cascades its direct conversations and ALL messages within them, including
the other participant's rows. Related report references become NULL; an SQL trigger clears the
description when either party is deleted. Minimal reason/status/times survive only until report
expiry. This choice prioritizes account erasure over the other participant retaining this history.
Steam-import clear does not delete chat or platform relationships. Tests verify both distinct paths.
No full chat dump/body is added to logs/audits; production backup erasure remains a deployment task.
