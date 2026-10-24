# ADR 0025 — Transactional platform graph and visible-evidence discovery

Status: Implemented in Phase 5; acceptance recorded separately.

Keep requests, accepted canonical connections, directional blocks, reports and notifications
as distinct entities. Sorted User pair locks serialize graph actions and coexist with the
accepted account privacy/deletion locks. A reverse pending request conflicts and requires
explicit acceptance; block terminates connection/pending state, and unblock never restores it.

Extend the shared player authorization projection with platform-connection facts, never Steam
friend grants. Filter candidate privacy and bilateral blocks before ranking. Use the documented
0..100 visible-evidence-v1 formula, capped pools, no exhaustive registry pagination and fail-closed
Redis quotas. Do not score private language/timezone or stale owner data.

Persist minimal deduplicated notification references and restricted 90-day reports. Deletion
redacts report text at the database boundary; explicit cleanup enforces the retention cutoff.
No chat/WebSockets, inferred social graph, cached authorization or automatic Steam request.

Tradeoffs: pair locks serialize actions involving the same user; discovery is bounded rather
than globally ranked; no public moderator UI or automated retention scheduler. These limits are
explicit for this local phase and must be revisited before public deployment.

See [exact invariants, matrix and policies](../architecture/SOCIAL_GRAPH.md).
