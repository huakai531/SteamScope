# ADR 0024: Session-authorized player reads and query-time comparison

Status: Accepted for Phase 4 local implementation, 2026-10-22 America/Los_Angeles.

Use `/users/{handle}` without UUID/SteamID public identity. Require session authentication;
`public` currently means other signed-in users. Connections-only is owner-only until an accepted
platform relationship system exists. Keep locale/timezone owner-only pending independent consent.

Enforce source exposure/freshness and resource preferences before projection, filtering and totals.
Use a consistent read-only database snapshot with session revalidation. Do not persist comparisons
or cache policy decisions. Bind cursor digests to viewer, target and visible result context.

Consequences: no migration/derived table; privacy changes apply to the next read; handle reuse
cannot reuse old cursor authorization. Owner stale evidence remains labelled, non-owner stale data
fails closed. Projection is bounded but in-memory; large-scale discovery optimization is deferred.

The executable contract, privacy matrix, frontend routes and overlap semantics are documented in
[Player views](../architecture/PLAYER_VIEWS.md). Phase 3 owner APIs and historical evidence remain
unchanged. Phase 5 may extend policy after explicit authorization; Steam friends never substitute
for platform connections.
