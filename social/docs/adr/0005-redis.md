# ADR-0005: Redis transient roles

Status: accepted design; future-phase behavior remains planned.

## Context

Cross-instance realtime delivery and expiring state need shared transient coordination.

## Decision

Redis for cache, rate limits, presence, typing and Pub/Sub; reconstruct from PostgreSQL.

## Alternatives considered

In-process-only state; Redis message persistence.

## Consequences

Redis loss degrades availability but does not erase durable business state.

## Revisit conditions

Delivery semantics or measured load require another transport.
