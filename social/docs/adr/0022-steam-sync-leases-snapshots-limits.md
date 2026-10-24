# ADR-0022: Owner-requested Steam snapshots and PostgreSQL leases

Status: implemented in Phase 3A; acceptance evidence is in the public validation summary.
Date: 2026-10-22. Supersedes the future-only status of ADR-0011 for the 3A resources only.

## Decision

The existing API enqueues one compatible full 3A import per owner. PostgreSQL's partial unique
index allows only one queued/running/retry job per user; authenticated handlers also serialize
on the user row. New jobs return 202; repeated active requests return 200 with the same UUID.
After the prior request, the default cooldown is 300 seconds (429), independent of job success.
GET never enqueues work. There is no arbitrary SteamID parameter or public data endpoint.

States: queued -> running -> succeeded / partial / failed, or running -> retry -> running.
Clearing/deletion cancels queued/running/retry jobs. Succeeded requires three validated populated
or confirmed-empty resources. Partial means at least one successful resource and another terminal
failure/unknown/restriction. Retry is not success. Terminal outcomes are not automatically refetched;
only unfinished/transient resources are retried. A fresh user request may revisit all resources.

The independent existing Worker selects eligible candidates and takes user then job row locks with
SKIP LOCKED. Claims commit before any HTTP call. Each claim has a random UUID token, an attempt
number and a default 90-second lease, using the database clock. Each resource's writes lock the
same user and job and verify active account, link UUID, Steam identity, import generation, token,
running status and unexpired lease. An additional expiry check before resource commit rolls back
an overlong write. A lost/expired claim cannot publish. Claims do not promise exactly-once HTTP;
processing is at least once and normalized writes replace only validated complete snapshots.

The client performs at most three sequential bounded (10-second total each) calls per claim.
No heartbeat is needed for this bounded batch; a slow DB or lost lease causes fenced rollback.
An abandoned running claim becomes eligible after expiry. Its run is marked lease_expired; after
the configured maximum (default 3 claims), it becomes partial/failed rather than looping forever.
Graceful stop cancels the fetch and releases the current claim to delayed retry; hard termination
uses lease recovery. A dependency outage pauses daemon work; readiness remains separately honest.

Retry delay is max(Retry-After/application quota delay, min(300, 5 * 2^attempt) + 0–3 seconds jitter).
HTTP 429 reserves a shared blocked-until timestamp. Missing/invalid configuration, access-denied,
ambiguous visibility and malformed responses are terminal for that resource, not endless retries.
Valid Retry-After values (seconds or HTTP date) are respected even above one day; values beyond
the supported integer range become a terminal unavailable outcome rather than an earlier retry.
An operator should investigate prolonged throttling instead of repeatedly initiating jobs. Request budgets count reserved calls,
including failures/crashes; reservations are never refunded.

## Durable application limits

One configured server key, with conservative shared budgets stored in PostgreSQL:
30 calls/minute, 1000 calls/day, 12 calls/owner/hour by default. Counters and 429 pauses survive
process restart and are serialized across workers. All workers using this database share the
same budget even after key rotation; the key or its hash is never stored. These are application
limits, not a statement of Valve's quota. They cannot account for unrelated applications using
the same key outside this database; the operator must use a project-specific standard user key.
Fixed UTC windows are bounded but may allow a boundary burst; the 300-second user cooldown and
shared minute cap remain in force. Redis still supports existing CSRF-adjacent write-rate limits;
it is not the durable queue or the Steam quota source of truth.

## Privacy and deletion serialization

The existing authenticated context holds the user row lock. Clear increments import_generation,
clears metadata and imported rows, cancels active claims/runs and removes resource states in one
transaction. Delete performs the same invalidation and then cascades account-owned tables.
Every worker write uses that lock order, so either the write precedes deletion and is removed, or
deletion wins and the write is rejected. An earlier pre-fetch existence check alone is insufficient.
There is no imported-data Redis cache. Browser queries are owner-scoped, uncached HTTP; clear resets
them and notifies other tabs, and session end hides the document, clears queries and navigates away.

## Alternatives and revisit conditions

In-memory jobs lose requests; Redis-only counters lose the durable quota across Redis resets;
Celery and a second worker add unnecessary infrastructure. Leases may repeat external calls but
avoid long transactions spanning the network. Revisit batch size/heartbeats before adding 3B
fan-out, and independently authorize 3B. No achievements, friendship or public player features
are included here.

## Phase 3B amendment

[ADR 0023](0023-selected-achievements-and-steam-friends.md) supersedes the single-active-user index
with scope/app deduplication and adds shared-schema leases. Base batches still have three resources;
3B is explicitly authorized separately, has at most two Steam calls for one selected game (one on
cache hit), or one friends call. All other fencing, timeout, quota and privacy decisions remain.
