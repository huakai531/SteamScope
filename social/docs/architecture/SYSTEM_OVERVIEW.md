# Architecture and trust boundaries

Phase 2 adds verified Steam OpenID identity, UUID users, server sessions, account/privacy UI,
revocation/deletion and minimal auditing to the Phase 1 foundation. Phase 3A implements owner-only
Steam profile/library/recent imports and durable jobs. Achievements/friends, public profiles, social
and chat remain planned. ADRs 0019–0022 describe implemented boundaries.

The modular monolith has one Python package `steamscope_social` installed from a src layout.
API and worker use the same image/package, different processes and commands. Next.js provides
the browser shell and a fixed-path status proxy. `INTERNAL_API_URL` is server-only;
browser requests use `/api/status` and allowlisted `/api/v1/*`. A static page build never requests the backend.
OpenAPI JSON and generated TypeScript describe implemented health/system/account contracts.

PostgreSQL owns durable state; Redis holds reconstructible cache, rate limits, presence,
typing and Pub/Sub. No message durability is assigned to Redis. Future message sends commit
before acknowledgement; reconnect reads the database. A bounded delivery retry record may
be added with chat if required; do not introduce a general event platform in Phase 1.

Trust boundaries: browser input is untrusted; the API validates and authorizes it. Steam
callbacks require provider verification, return-target binding and nonce replay protection.
API/worker secrets stay server-side. External payloads are validated before transactions.
The database and Redis bind only to loopback when published by development Compose.
Only authorized service code writes a module's tables. Never keep a DB transaction open
while waiting for Steam HTTP. See MODULE_BOUNDARIES for call direction.

Failure boundaries: API liveness survives dependency outages; readiness probes PostgreSQL
and Redis concurrently within per-dependency deadlines. Frontend status reports upstream
unavailability safely. Worker exits nonzero if its initial dependencies fail, then periodically
checks them while idle. Phase 3 adds leases, retry and ownership fencing. Redis failure
degrades realtime delivery, never deletes PostgreSQL messages. Deleted/inactive accounts
must fence all pending and in-flight jobs before writes.

See DIAGRAMS.md (eight diagrams), database/DATA_MODEL.md (full MVP), api/API_OUTLINE.md,
and security/THREAT_MODEL.md. Phase 2 creates six baseline tables; Phase 3A adds seven current
Steam sync tables and metadata columns. All later roadmap entities remain unimplemented.

Phase 3A data flow: authenticated same-origin owner action -> API enqueue -> PostgreSQL durable
claim -> independent existing Worker -> bounded Steam HTTPX client -> full snapshot validation ->
fenced resource transaction -> owner-only read API -> My Steam Data. Redis is not the queue.
See STEAM_DATA_FLOW and ADR-0022 for privacy/freshness/lease/deletion boundaries.
