# ADR-0013: WebSockets for realtime

Status: accepted design; future-phase behavior remains planned.

## Context

MVP requires interactive delivery, typing and presence.

## Decision

Phase 6 uses authenticated sockets with per-event authorization and REST history.

## Alternatives considered

Polling-only; Steam PM integration.

## Consequences

Revoked sessions and blocks affect existing sockets; reconnect must backfill.

## Revisit conditions

Operating environment cannot support persistent connections.
