# ADR 0026 — Persistent direct chat with transient delivery

Status: accepted for Phase 6 implementation; local acceptance tracked separately.
Date: 2026-10-23 America/Los_Angeles.

Decision: canonical UUID pairs, database membership/sequence/idempotency constraints and the
existing ordered user/session locks govern plain-text direct chat. REST owns durable sends and
commits before any Redis hint or HTTP success. Cookie-authenticated same-origin WebSockets carry
reauthorized delivery hints and bounded presence/typing. Redis is not a message repository.

Connection removal preserves participant history but disables sends; block hides conversation
access. Reconnection reuses the pair. Session/policy changes are checked on operations and every
second on sockets, with an 8-second tested revocation target. Retry uses the same client UUID;
history plus cursor reconciliation recover dropped events and committed-but-unacknowledged sends.

Consequences: no exactly-once transport, durable Redis queue or end-to-end encryption claim.
The model is suitable for a local MVP; one Pub/Sub subscription per socket and periodic DB policy
checks are deliberately simple and have not been load-tested. Notification WS delivery and a
moderator UI remain outside this explicit Phase 6 scope. Erasure, rates, schemas, reconnect and
multi-tab TTL semantics are specified in [DIRECT_CHAT](../architecture/DIRECT_CHAT.md).
