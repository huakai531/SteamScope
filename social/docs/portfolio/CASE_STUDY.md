# SteamScope

**A Steam-data-driven social platform**

[Project overview](../../README.md) · [Architecture](ARCHITECTURE_OVERVIEW.md) · [Demo](PROFESSOR_DEMO.md)

Accepted implementation baseline: `4f8938d74455799d1712aa5fa670fe14f7eab675`, locally verified through Phase 6 on 2026-10-23. This case study describes that implementation; it does not announce a public launch.

## Problem

Finding someone to play with usually starts with limited context: a name, an invitation or a short message. A player's library, time spent in shared games and achievement history can make that introduction more meaningful. However, those signals are incomplete and privacy-sensitive. A missing response is not proof that someone owns no games or has unlocked nothing.

## Product idea

SteamScope turns Steam data into social context. A verified identity leads to an understandable player profile; authorized gaming overlap informs discovery; an explicit connection leads to a private conversation. Chinese gaming community products such as Xiaoheihe inspired the product model, but SteamScope is an independent implementation with no affiliation to Xiaoheihe or Valve.

## Goals

- Deliver a complete identity-to-conversation journey rather than disconnected API examples.
- Give players useful context without revealing hidden data through totals or rankings.
- Make imported data and messages survive process failures, retries and browser refreshes.
- Make design decisions inspectable through migrations, contracts, tests and recorded acceptance evidence.

## Constraints

The target is a local university/portfolio MVP. Steam is an external dependency with its own visibility rules and error modes. The implementation keeps the existing legacy project separate, uses one modular backend codebase, and runs five local services. Tests must use isolated databases and deterministic provider fixtures without live Steam calls.

Scope excludes group chat, media uploads, voice/video, communities and Looking for Group. Production deployment, load validation, remote CI execution and moderation operations remain separate work. The specific former dependency exception is closed following upstream advisory withdrawal; see the current security record.

## Architecture

Next.js provides the UI and same-origin API/WebSocket forwarding. FastAPI owns authorization and domain operations. PostgreSQL is the source of truth for accounts, snapshots, jobs, social relationships and messages. Redis supports rate limits, Pub/Sub and expiring presence/typing. The Worker claims persistent synchronization jobs and performs bounded Steam Web API requests.

The modular monolith makes cross-domain transactions and privacy rules practical to inspect. Separating the Worker avoids holding an interactive browser request open while Steam resources are fetched. [Architecture diagrams and source map](ARCHITECTURE_OVERVIEW.md)

## Core features

Players can authenticate through Steam, maintain independent SteamScope profiles, synchronize permitted gaming data, compare visible mutual games, search/discover players, request connections and exchange persistent direct messages. Blocking, reporting, notifications, session management, Steam-data clearing and account deletion complete the local interaction loop.

The implementation scope is concrete and reviewable:

| Area       | What the repository demonstrates                                                | Presenter should be able to explain                               |
| ---------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Identity   | Verified OpenID linkage, UUID users and revocable sessions                      | Why an external identity is separate from session authority       |
| Data       | Durable jobs, resource snapshots and shared achievement schemas                 | How stale, empty and unknown differ                               |
| Social     | Authorized projections, deterministic discovery and transactional relationships | Why privacy checks precede scoring                                |
| Chat       | Canonical conversations, persistent messages and transient socket delivery      | What happens after commit if acknowledgement is lost              |
| Validation | Real-service tests, browser flows and distinct live-user evidence               | Which claims are automated, observed by users or still unverified |

This table describes project implementation, not proof that every line was independently handwritten by one person. A submission should state the presenter's actual contribution and any assistance according to course requirements; the repository cannot establish personal authorship or learning by itself.

## Steam integration

OpenID verifies account identity without requiring a Web API key. Owner-requested imports use server-only configuration and fixed Steam endpoints. Profile, library, recent activity, selected-game achievements and friend snapshots have independent outcomes and freshness policies.

Shared achievement definitions are separated from player progress. A schema can be readable while personal statistics are restricted. Exact completion requires a fresh compatible schema, complete progress and explicit known states. Stale owner rows can remain historical without displaying a misleading percentage.

Live validation made this distinction tangible: a personal achievement request returned `HTTP 403 / PROFILE_NOT_PUBLIC`. The user reported that Game details was Friends Only, then changed that setting to Public. Subsequent personal snapshots succeeded. Server evidence confirms the denial and later success; the settings inspection/change is **USER VERIFIED**. This verifies source privacy enforcement, not a privacy bypass. [Recorded live evidence](../development/VALIDATION.md)

## Social graph design

Imported Steam friends and SteamScope connections are different graphs. A verified external friendship does not automatically grant platform access. A directed connection request needs the recipient's explicit acceptance. The resulting relationship is stored as one canonical ordered UUID pair.

Ordered locks, transactions and database constraints handle reverse requests, repeated acceptance and races with blocking. Blocking cancels pending requests and removes the platform connection. Unblocking removes the block only; it does not recreate consent. Persistent notifications have their own event identity to prevent logical duplicates.

Discovery uses a bounded candidate pool and a documented formula over visible mutual games, permitted activity/playtime evidence and eligible imported-friend matches. Explanations describe the evidence actually used. The system does not claim machine-learning personalization or a global optimum. [Social design](../architecture/SOCIAL_GRAPH.md)

## Real-time messaging

A sender creates a client message ID. The server validates membership and current relationship policy, commits the message, and then publishes a hint. Another API instance can receive that Redis hint and notify an authorized socket. The recipient reads the canonical history from PostgreSQL.

If a hint is lost, reconnect and cursor-based gap recovery find the committed message. If acknowledgement is lost, the same sender/client ID returns the same logical message. Read cursors survive refresh and only advance. Typing and presence expire and are not stored as message history. Presence means an active SteamScope connection, not “currently playing on Steam.”

Existing sockets revalidate sessions and policy; a local eight-second revocation target is tested. Already delivered packets cannot be retracted, and this is not an absolute distributed timing guarantee. [Chat contract](../architecture/DIRECT_CHAT.md)

## Privacy and safety

Visibility is enforced on the server before projection and aggregation. Platform preferences intersect with source exposure and freshness. Anonymous access is not enabled by the application's “public” setting. Cookie sessions, CSRF/origin checks, membership checks, plain-text rendering and limits form separate layers.

Messages have a documented tombstone policy. Reports reference messages rather than copying their content. Steam-data clearing preserves platform chat; deleting an account removes its paired conversations and follows the report-redaction policy. Explicit cleanup is required for expired retained data; no unattended retention scheduler or moderator console is claimed. [Privacy](../security/PRIVACY_MODEL.md) · [Erasure](../security/DATA_RETENTION_AND_DELETION.md)

## Major technical challenges

| Challenge                                                                            | Decision and result                                                                                              | Evidence                                                                  |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Steam privacy:** identity is verified while individual resources remain restricted | Store resource-specific status; preserve Unknown instead of manufacturing locked achievements or zero completion | Real privacy denial/positive transition; source-boundary tests            |
| **Durable synchronization:** retries or late responses may overwrite newer state     | Persist jobs; claim with leases/tokens; fence writes against link/generation/lease; bound retries                | Two-claimer, stale-worker, interrupted-process and clear/delete tests     |
| **Privacy-safe discovery:** even an aggregate can disclose a hidden fact             | Authorize rows and fields before counts, intersections and scoring                                               | Privacy matrix and automated multi-user comparison/discovery              |
| **Real-time reliability:** sockets and Pub/Sub may lose events                       | Commit first; deliver hints; reconcile durable cursor gaps                                                       | Two API instances, dropped delivery, offline browser and recovery tests   |
| **Message duplication:** a successful write may lose its acknowledgement             | Unique sender/client ID plus one creation service                                                                | Immediate/concurrent retries and an actual test-process exit after commit |
| **Social concurrency:** opposing requests or accepts may produce inconsistent pairs  | Canonical pair keys, ordered locks, atomic transitions and constraints                                           | Acceptance/block/removal races and notification deduplication             |

These solutions are correctness mechanisms, not throughput benchmarks. No measured production scale is inferred from the number of tests.

## Testing

The historical accepted Phase 6 implementation run (2026-10-23) recorded **313 backend**, **45 frontend unit** and **20 full browser** tests passing. It includes unit checks, real PostgreSQL/Redis integration, migrations, concurrency, actual sockets across API instances, privacy matrices, frontend tests and Playwright flows. Separate container tests stopped/restored each dependency while preserving data and checked health/Worker recovery.

Tests use synthetic identities and provider fixtures in isolated resources. They establish repeatable behavior, not real-user adoption. The independent 2026-10-24 candidate run passed **313 backend**, **59 frontend unit** and **36 browser** tests, with separate targeted capture checks. See the [validation summary](../development/VALIDATION.md) for actual commands, warnings and boundaries.

## Results

**Local MVP complete:** Steam login → saved Steam data → player profile → discovery → connection → real-time chat.

| Evidence type   | Verified outcome                                                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| USER VERIFIED   | Real login, library/playtime correspondence, achievement states, source-privacy transition and persisted owner views                     |
| USER VERIFIED   | Two real users connected, exchanged live messages, refreshed retained history, and checked read/typing/presence/block/unblock behavior   |
| SERVER VERIFIED | Saved Steam snapshots/job outcomes; one direct conversation, persisted messages, coherent read cursors and no duplicate logical messages |
| AUTOMATED       | Broader authorization, privacy, concurrency, failure/recovery and multi-user behavior in isolated tests                                  |

The live Steam friend path was confirmed empty, matching the user's account; it was not a nonempty friend-import demonstration. Real two-user comparison was not separately verified. The portfolio screenshots are separately reviewed synthetic illustrations, not real account captures.

The [remote validation run](https://github.com/huakai531/SteamScope/actions/runs/40084501360) passed on 2026-10-24 using isolated services and deterministic fixtures; this is separate from live-user evidence. On 2026-10-24, full and production npm audits both returned exit 0 / 0 findings. The former braces exception is resolved because the official advisory was withdrawn, not because its dependency path disappeared. Historical failed audits remain preserved. [Current security status](../security/CURRENT_SECURITY_STATUS.md)

## What I learned

The engineering lessons demonstrated by this implementation are:

- Model knowledge as well as values: unknown, empty, stale and denied have different product meanings.
- Put invariants in the database and transaction boundaries, not only in disabled UI buttons.
- Treat a WebSocket event as a delivery hint; recover from durable state rather than assuming an event arrived.
- Evaluate privacy before computing summaries, because a score can reveal information without showing a raw field.
- Separate automated evidence, user observations and server verification; one does not silently substitute for another.

For a personal reflection, connect each lesson to a decision or debugging episode the presenter actually handled. These are project-level lessons, not an invented account of the student's individual experience.

## Next steps

Review the prepared synthetic screenshot set and rehearse the five-minute local demo. A later implementation scope may add game communities and Looking for Group. Production hardening requires its own dependency decision, remote CI evidence, monitoring, backup/retention operations and load validation before deployment. None of that work starts as part of this packaging task.
