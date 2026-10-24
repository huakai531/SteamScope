# ADR-0023: Selected-game snapshots, shared English schemas and owner-only Steam edges

Status: implemented; local acceptance passed. Historical automated checks, real achievements/privacy transition and confirmed-empty friends evidence are separated in the public validation summary; the historical local-development dependency exception is closed; see the current security status.
Date: 2026-10-22. Extends ADR 0022, supersedes its single-active-user deduplication only.

## Decision

Use existing jobs/runs, with scope base/0, friends/0 or achievements/app_id. An active scoped job is
reused; per-owner active cap 5 and scoped cooldown 300s complement unchanged global/per-owner call
budgets. No login, base sync or GET fans out to new resources. App eligibility is checked when
enqueuing, claiming and publishing against the owner's exposed imported library.

Shared `(app_id, english)` schemas have default 86400s TTL, canonical revision and 30s lease. Misses
reserve shared budget under existing owner/job fences; transactions commit before HTTP. A second
owner waits or reuses a validated hit. Cache failures retain old definitions/success and impose at
least 60s retry pause. Recheck both job and cache tokens/expiry after HTTP. Metadata/definition reads
and personal reconciliation briefly lock the same schema row, avoiding mixed-revision reads.

Player snapshots bind to the captured schema revision; exact IDs and explicit booleans are required
for a fresh exact percentage. No definition FK may cascade personal progress. Unknown identifiers
remain represented; resets/removals follow complete snapshots. Uncertain coverage yields null
percentage; zero definitions is not 100%. Hidden descriptions require owner reveal; icon placeholders
avoid an image-fetch/proxy surface.

Friend edges belong to the importing user, not another local account. Complete validated snapshots
alone reconcile removals. Endpoint-aware 401 preserves private-or-unauthorized uncertainty. Server
reads hide rows/counts/cursors together on denied/unknown results or expiry; there is no public API,
enrichment, discovery or relationship side effect.

Clear/delete acquires the existing owner lock, increments generation, cancels work, erases new
personal rows/states and non-base histories, and releases associated cache lease tokens. A stale
HTTP result cannot restore data. Shared definitions survive one owner's deletion. Reads never import.

## Consequences and alternatives

One selected game bounds requests and preserves source uncertainty. English-only avoids localization
cache mixing; missing API metadata cannot be fabricated. A separate task service/Redis queue,
automatic library-wide achievement scan, recursive friendship crawl and event-sourced schemas add
scope or privacy risks without this phase's need. Schema calls may repeat after crashes (at-least-once),
but fencing prevents obsolete writes. Failed shared refresh may temporarily suppress exact percentages
for multiple owners; a later explicit job can refresh. Revisit TTL/languages/batch sizes only with
separate requirements and tests. No public deployment or Phase 3C authorization is implied.
